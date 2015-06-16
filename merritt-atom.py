#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, os
import argparse
from lxml import etree
from pynux import utils
from datetime import datetime
import dateutil.tz
import pprint

""" Given the Nuxeo document path for a collection folder, publish ATOM feed for objects for Merritt harvesting. """
pp = pprint.PrettyPrinter()
PER_PAGE = 50
ATOM_NS = "http://www.w3.org/2005/Atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
NX_NS = "http://www.nuxeo.org/ecm/project/schemas/tingle-california-digita/ucldc_schema"
NS_MAP = {None: ATOM_NS,
          "nx": NX_NS,
          "dc": DC_NS}

class MerrittAtom():

    def __init__(self, path, pynuxrc='~/.pynuxrc-prod'):
        self.path = path
        self.nx = utils.Nuxeo(rcfile=pynuxrc)

    def _extract_nx_metadata(self, uid): 
        ''' extract Nuxeo metadata we want to post to the ATOM feed '''
        raw_metadata = self.nx.get_metadata(uid=uid)
        metadata = {}
        
        # creator
        creators = raw_metadata['properties']['ucldc_schema:creator']
        metadata['creator'] = [creator['name'] for creator in creators]

        # title
        metadata['title'] = raw_metadata['title']

        # date
        dates = raw_metadata['properties']['ucldc_schema:date']
        dates = [date['date'] for date in dates]
        metadata['date'] = dates[0] if dates else None

        # nuxeo id
        metadata['id'] = raw_metadata['properties']['ucldc_schema:identifier']

        # nuxeo collection
        metadata['collection'] = raw_metadata['properties']['ucldc_schema:collection'][0] if raw_metadata['properties']['ucldc_schema:collection'] else None

        return metadata

    def _add_atom_elements(self, doc):
        ''' add atom feed elements to document '''
        # required ATOM feed elements
        feed_id = etree.SubElement(doc, etree.QName(ATOM_NS, "id"))
        feed_id.text = "http://nuxeo.cdlib.org" 

        feed_title = etree.SubElement(doc, etree.QName(ATOM_NS, "title"))
        feed_title.text = "UCLDC Metadata Feed" # FIXME get campus name from registry API?

        feed_updated = etree.SubElement(doc, etree.QName(ATOM_NS, "updated"))
        feed_updated.text = datetime.now(dateutil.tz.tzutc()).isoformat()

        # recommended ATOM feed elements
        feed_author = etree.SubElement(doc, etree.QName(ATOM_NS, "author"))
        feed_author.text = "UC Libraries Digital Collection"

        return doc 

    def _add_collection_alt_link(self, doc, path):
        ''' add elements related to Nuxeo collection info to document '''
        collection_metadata = self.nx.get_metadata(path=path)
        collection_title = collection_metadata['title']
        collection_uid = collection_metadata['uid']
        collection_uri = self.get_object_view_url(collection_uid)

        feed_link_alt = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="alternate", href=collection_uri, title=collection_title) 

        return doc

    def _add_paging_info(self, doc):
        ''' add rel links for paging '''
        # this is just dumb for now
        self_link = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="self", href="https://s3.amazonaws.com/static.ucldc.cdlib.org/merritt/nx_mrt_sample.atom")
        first_link = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="first", href="https://s3.amazonaws.com/static.ucldc.cdlib.org/merritt/nx_mrt_sample.atom")
        prev_link = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="previous", href="https://s3.amazonaws.com/static.ucldc.cdlib.org/merritt/nx_mrt_sample.atom")
        next_link = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="next", href="https://s3.amazonaws.com/static.ucldc.cdlib.org/merritt/nx_mrt_sample.atom")
        last_link = etree.SubElement(doc, etree.QName(ATOM_NS, "link"), rel="last", href="https://s3.amazonaws.com/static.ucldc.cdlib.org/merritt/nx_mrt_sample.atom")

    def _add_merritt_id(self, doc, merritt_collection_id):
        ''' add Merritt ID '''
        merritt_id = etree.SubElement(doc, etree.QName(ATOM_NS, "merritt_collection_id"))
        merritt_id.text = merritt_collection_id 

    def _populate_entry(self, entry, metadata, nxid):
        ''' get <entry> element for a given set of object metadata '''

        # atom id (URI)
        nuxeo_object_view_url = self.get_object_view_url(nxid)
        atom_id = etree.SubElement(entry, etree.QName(ATOM_NS, "id"))
        atom_id.text = nuxeo_object_view_url

        # atom title
        atom_title = etree.SubElement(entry, etree.QName(ATOM_NS, "title"))
        atom_title.text = metadata["title"]
 
        # atom updated
        atom_updated = etree.SubElement(entry, etree.QName(ATOM_NS, "updated"))
        atom_updated.text = datetime.now(dateutil.tz.tzutc()).isoformat()

        # atom author
        atom_author = etree.SubElement(entry, etree.QName(ATOM_NS, "author"))
        atom_author.text = "UC Libraries Digital Collection"

        # atom links - Merritt is reading the component objects from here
        full_metadata_url = self.get_full_metadata(nxid)
        link_md = etree.SubElement(entry, etree.QName(ATOM_NS, "link"), rel="alternate", href=full_metadata_url, type="application/xml", title="Full metadata for this object from Nuxeo")

        media_json_url = self.get_media_json_url(nxid)
        link_media_json = etree.SubElement(entry, etree.QName(ATOM_NS, "link"), rel="alternate", href=media_json_url, type="application/json", title="Deep Harvest metadata for this object")

        nxpath = self.nx.get_metadata(uid=nxid)['path']
        nuxeo_file_download_url = self.get_object_download_url(nxid, nxpath)
        link_object_file = etree.SubElement(entry, etree.QName(ATOM_NS, "link"), rel="alternate", href=nuxeo_file_download_url) # FIXME add content_type

        # dc creator
        for creator_name in metadata['creator']:
            dc_creator = etree.SubElement(entry, etree.QName(DC_NS, "creator"))
            dc_creator.text = creator_name 

        # dc title
        dc_title = etree.SubElement(entry, etree.QName(DC_NS, "title"))
        dc_title.text = metadata['title']

        # dc date
        dc_date = etree.SubElement(entry, etree.QName(DC_NS, "date"))
        dc_date.text = metadata['date']

        # dc identifier (a.k.a. local identifier) - Nuxeo ID
        nuxeo_identifier = etree.SubElement(entry, etree.QName(DC_NS, "identifier"))
        nuxeo_identifier.text = nxid

        # UCLDC identifier (a.k.a. local identifier) - ucldc_schema:identifier -- this will be the ARK if we have it
        if metadata['id']:
            ucldc_identifier = etree.SubElement(entry, etree.QName(NX_NS, "identifier"))
            ucldc_identifier.text = metadata['id']

        # UCLDC collection identifier
        ucldc_collection_id = etree.SubElement(entry, etree.QName(NX_NS, "collection"))
        ucldc_collection_id.text = metadata['collection']

        return entry

    def _publish_feed(self, doc):
        ''' publish feed '''
        feed = etree.ElementTree(doc)
        xml_declaration = etree.ProcessingInstruction('xml', 'version="1.0" encoding="utf-8"')
        xml_declaration_string = etree.tostring(xml_declaration, encoding=unicode)
        feed_string = etree.tostring(feed, pretty_print=True, encoding=unicode)

        with open("nx_mrt_sample.atom", "w") as f:
            f.write(xml_declaration_string)
            f.write('\n')
            f.write(feed_string)
      
        # TODO host feed

    def get_object_view_url(self, nuxeo_id):
        """ Get object view URL """
        url = "https://nuxeo-stg.cdlib.org/Nuxeo/nxdoc/default/{0}/view_documents".format(nuxeo_id)
        
        return url

    def get_structural_metadata(self, nuxeo_id):
        """ Get media.json file. See https://github.com/ucldc/ucldc-docs/wiki/media.json """
        url = "http://s3url.aws.com/{0}-media.json".format(nuxeo_id) # FIXME
        
        return url

    def get_full_metadata(self, nuxeo_id):
        """ Get full metadata via Nuxeo API """
        url = "https://nuxeo-stg.cdlib.org/Nuxeo/restAPI/default/{0}/export?format=XML".format(nuxeo_id)
    
        return url

    def get_object_download_url(self, nuxeo_id, nuxeo_path):
        """ Get object file download URL """
        filename = nuxeo_path.split('/')[-1]
        url = "https://nuxeo-stg.cdlib.org/Nuxeo/nxbigfile/default/{0}/file:content/{1}".format(nuxeo_id, filename)
    
        return url

    def get_media_json_url(self, nuxeo_id):
        """ Get media.json (deep harvest) url """
        # https://s3.amazonaws.com/static.ucldc.cdlib.org/media_json/002130a5-e171-461b-a41b-28ab46af9652-media.json
        url = "https://s3.amazonaws.com/static.ucldc.cdlib.org/media_json/{}-media.json".format(nuxeo_id)

        return url

def main(argv=None):
    parser = argparse.ArgumentParser(description='Create ATOM feed for a given Nuxeo folder for Merritt harvesting')
    parser.add_argument("path", help="Nuxeo document path")
    parser.add_argument("--pynuxrc", help="rc file for use by pynux")
    if argv is None:
        argv = parser.parse_args()
    nx_path = argv.path

    if argv.pynuxrc:
        ma = MerrittAtom(nx_path, pynuxrc)
    else:
        ma = MerrittAtom(nx_path)

    documents = ma.nx.children(nx_path) # assuming simple objects only
    nxids = [document['uid'] for document in documents]

    # FIXME move this logic into MerrittAtom class
    # create root
    root = etree.Element(etree.QName(ATOM_NS, "feed"), nsmap=NS_MAP)

    # add header info
    ma._add_atom_elements(root)
    ma._add_collection_alt_link(root, ma.path)
    ma._add_paging_info(root)
    ma._add_merritt_id(root, "ark:/13030/m5rn35s8") # FIXME

    # add entries
    for nxid in nxids:
        nx_metadata = ma._extract_nx_metadata(nxid)
        entry = etree.SubElement(root, etree.QName(ATOM_NS, "entry"))
        entry = ma._populate_entry(entry, nx_metadata, nxid)        

    ma._publish_feed(root)

if __name__ == "__main__":
    sys.exit(main())
