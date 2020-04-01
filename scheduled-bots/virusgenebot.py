# -*- coding: utf-8 -*-
"""VirusGeneBot.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1WrnCPtpA6lPSY5F8aN-JZxGRXy-ZPrZi

**Authors:**
  - Jasper Koehorst (ORCID:0000-0001-8172-8981 )
  - Andra Waagmeester (ORCID:0000-0001-9773-4008)
  - Egon Willighagen (ORCID:0000-0001-7542-0286)

This bot uses of the [WikidataIntegrator](https://github.com/SuLab/WikidataIntegrator).

Taxa ran: 
[2697049](https://www.ncbi.nlm.nih.gov/taxonomy/2697049), 
[1415852](https://www.ncbi.nlm.nih.gov/taxonomy/1415852), 
[227859](https://www.ncbi.nlm.nih.gov/taxonomy/227859), 
[349342](https://www.ncbi.nlm.nih.gov/taxonomy/349342), 
[305407](https://www.ncbi.nlm.nih.gov/taxonomy/305407), 
[1335626](https://www.ncbi.nlm.nih.gov/taxonomy/1335626)

This bot is a first attempt to automatically maintain genomics data on Wikidata from authoritittive resources on the 
SARS-CoV-2 virus. SARS-CoV-2 belongs to the broad family of viruses known as coronaviruses. This bot addresses the
seven known coronavirus to infect people.

The bot roughly works as follows:
1. Check if the taxonid of the virus is already covered in Wikidata
2. Get list of genes from https://mygene.info/
3. Create or check items on Wikidats for each annotated gene

The bot aligns with the following schema: https://www.wikidata.org/wiki/EntitySchema:E165

### Dependency installation
To add data to wikidata the wikidata integrator application is used.

Fetching and parsing protein information is achieved through the BioPython package
"""

"""### Wikidata variables
A username and password are required to authenticate with WikiData.org
"""



"""## Dependencies and functions"""

import copy
import json
import os
import pprint
from datetime import datetime
import requests
from wikidataintegrator import wdi_core, wdi_login
from rdflib import Graph, URIRef
from Bio import Entrez,SeqIO
import ftplib
import urllib.request
import gzip
import re


# Wikidata provenance reference for NCBI Taxonomy
def createNCBITaxReference(ncbiTaxId, retrieved):
    refStatedIn = wdi_core.WDItemID(value="Q13711410", prop_nr="P248", is_reference=True)
    timeStringNow = retrieved.strftime("+%Y-%m-%dT00:00:00Z")
    refRetrieved = wdi_core.WDTime(timeStringNow, prop_nr="P813", is_reference=True)
    refNcbiTaxID = wdi_core.WDString(value=ncbiTaxId, prop_nr="P685", is_reference=True)
    ncbi_reference = [refStatedIn, refRetrieved, refNcbiTaxID]
    return ncbi_reference

# Wikidata provenance reference for NCBI Gene
def createNCBIGeneReference(ncbiGeneId, retrieved):
    refStatedIn = wdi_core.WDItemID(value="Q20641742", prop_nr="P248", is_reference=True)
    timeStringNow = retrieved.strftime("+%Y-%m-%dT00:00:00Z")
    refRetrieved = wdi_core.WDTime(timeStringNow, prop_nr="P813", is_reference=True)
    refNcbiGeneID = wdi_core.WDString(value=ncbiGeneId, prop_nr="P351", is_reference=True)

    ncbi_reference = [refStatedIn, refRetrieved, refNcbiGeneID]
    return ncbi_reference

# Wikidata provenance reference for UniProt
def createUniprotReference(uniprotId, retrieved):
    refStatedIn = wdi_core.WDItemID(value="Q905695", prop_nr="P248", is_reference=True)
    timeStringNow = retrieved.strftime("+%Y-%m-%dT00:00:00Z")
    refRetrieved = wdi_core.WDTime(timeStringNow, prop_nr="P813", is_reference=True)
    refUniprotID = wdi_core.WDString(value=uniprotId, prop_nr="P352", is_reference=True)

    reference = [refStatedIn, refRetrieved, refUniprotID]
    return reference

# Obtaining the Wikidata Gene identifier via the NCBI gene id
def getGeneQid(ncbiId, ncbi_reference):
    # Parent taxon
    gene_statements = [
    wdi_core.WDString(value=ncbiId, prop_nr="P351", references=[copy.deepcopy(ncbi_reference)])]
    return wdi_core.WDItemEngine(data=gene_statements)

# Obtain the WikiData item 
def getTaxonItem(taxonQid):
    return wdi_core.WDItemEngine(wd_item_id=taxonQid)
    
# Obtaining the item from the taxon id and creat the item
def set_taxon(taxid):
  ncbiTaxon = json.loads(requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=taxonomy&id={}&format=json".format(taxid)).text)
  taxonitemStatements = []
  ncbiTaxref = createNCBITaxReference(taxid, retrieved)
  ## instance of
  taxonitemStatements.append(wdi_core.WDItemID(value="Q16521", prop_nr="P31", references=[copy.deepcopy(ncbiTaxref)]))
  ## NCBI tax id
  taxonitemStatements.append(wdi_core.WDExternalID(value=taxid, prop_nr="P685", references=[copy.deepcopy(ncbiTaxref)]))
  ## scientificname
  scientificName = ncbiTaxon["result"][taxid]['scientificname']
  taxonitemStatements.append(wdi_core.WDString(scientificName, prop_nr="P225", references=[copy.deepcopy(ncbiTaxref)]))
  item = wdi_core.WDItemEngine(data=taxonitemStatements)
  if item.get_label() == "":
      item.set_label(label=scientificName, lang="en")
  if item.get_label() != scientificName:
      item.set_aliases(aliases=[scientificName])
  if item.get_description(lang="en") == "":
      item.set_description(description="strain of virus", lang="en")

  return item


def create_or_update_uniprot_protein_item(geneid, uniprotID):
    retrieved = datetime.now()
    ncbi_reference = createNCBIGeneReference(hit["entrezgene"], retrieved)
    uniprot_reference = createUniprotReference(uniprotID, retrieved)
    query = """
        PREFIX uniprotkb: <http://purl.uniprot.org/uniprot/>
        SELECT * WHERE {
        SERVICE <https://sparql.uniprot.org/sparql> {
            VALUES ?database {<http://purl.uniprot.org/database/PDB> <http://purl.uniprot.org/database/RefSeq>}
            uniprotkb:""" + uniprotID + """ rdfs:label ?label ;
            rdfs:seeAlso ?id .
            ?id <http://purl.uniprot.org/core/database> ?database .
        }}"""
    print(query)

    results = wdi_core.WDItemEngine.execute_sparql_query(query, endpoint="https://sparql.uniprot.org/sparql")
    refseq = []
    pdb = []
    for result in results["results"]["bindings"]:
        protein_label = result["label"]["value"]
        if result["database"]["value"] == "http://purl.uniprot.org/database/RefSeq":
            if result["id"]["value"].replace("http://purl.uniprot.org/refseq/", "") not in refseq:
                refseq.append(result["id"]["value"].replace("http://purl.uniprot.org/refseq/", ""))
        if result["database"]["value"] == "http://purl.uniprot.org/database/PDB":
            if result["id"]["value"].replace("http://rdf.wwpdb.org/pdb/", "") not in pdb:
                pdb.append(result["id"]["value"].replace("http://rdf.wwpdb.org/pdb/", ""))

    statements = []

    # Instance of protein
    statements.append(wdi_core.WDItemID(value="Q8054", prop_nr="P31", references=[copy.deepcopy(uniprot_reference)]))

    # encoded by
    geneitem = getGeneQid(geneid, ncbi_reference)
    geneqid = geneitem.wd_item_id
    statements.append(wdi_core.WDItemID(value=geneqid, prop_nr="P702", references=[copy.deepcopy(ncbi_reference)]))

    # found in taxon
    geneJson = geneitem.get_wd_json_representation()
    taxonQID = geneJson['claims']["P703"][0]["mainsnak"]["datavalue"]["value"]["id"]
    statements.append(wdi_core.WDItemID(taxonQID, prop_nr="P703", references=[copy.deepcopy(ncbi_reference)]))

    # exactMatch
    statements.append(wdi_core.WDUrl("http://purl.uniprot.org/uniprot/" + uniprotID, prop_nr="P2888",
                                     references=[copy.deepcopy(uniprot_reference)]))

    ## Identifier statements
    # uniprot
    statements.append(wdi_core.WDString(uniprotID, prop_nr="P352", references=[copy.deepcopy(uniprot_reference)]))
    # refseq
    for id in refseq:
        statements.append(wdi_core.WDString(id, prop_nr="P637", references=[copy.deepcopy(uniprot_reference)]))

    # pdb
    for id in pdb:
        statements.append(wdi_core.WDString(id, prop_nr="P638", references=[copy.deepcopy(uniprot_reference)]))
    taxonname = getTaxonItem(geneJson['claims']["P703"][0]["mainsnak"]["datavalue"]["value"]["id"]).get_label(lang="en")
    protein_item = wdi_core.WDItemEngine(data=statements)
    if protein_item.get_label(lang="en") == "":
        protein_item.set_label(protein_label, lang="en")
    if protein_item.get_description(lang="en") == "":
        protein_item.set_description("protein in " + taxonname, lang="en")
    if protein_item.get_description(lang="de") == "":
        protein_item.set_description("Eiweiß in " + taxonname, lang="de")
    if protein_item.get_description(lang="nl") == "":
        protein_item.set_description("eiwit in " + taxonname, lang="nl")
    if protein_item.get_description(lang="es") == "":
        protein_item.set_description("proteína en " + taxonname, lang="es")
    if protein_item.get_description(lang="it") == "":
        protein_item.set_description("Proteina in " + taxonname, lang="it")

    print(protein_item.get_wd_json_representation())
    protein_qid = protein_item.write(login)
    print(protein_qid)

    ## add the newly create protein item to the gene item
    encodes = [wdi_core.WDItemID(protein_qid, prop_nr="P688", references=[copy.deepcopy(ncbi_reference)])]
    geneitem = wdi_core.WDItemEngine(wd_item_id=geneqid, data=encodes)
    return geneitem.write(login)


def create_or_update_refseq_protein_item(geneid, refseqID):
    statements = []
    retrieved = datetime.now()
    ncbi_reference = createNCBIGeneReference(hit["entrezgene"], retrieved)
    pdb = []
    # Instance of protein
    statements.append(wdi_core.WDItemID(value="Q8054", prop_nr="P31", references=[copy.deepcopy(ncbi_reference)]))

    # encoded by
    geneitem = getGeneQid(geneid, ncbi_reference)
    geneqid = geneitem.wd_item_id
    statements.append(wdi_core.WDItemID(value=geneqid, prop_nr="P702", references=[copy.deepcopy(ncbi_reference)]))

    # found in taxon
    geneJson = geneitem.get_wd_json_representation()
    taxonQID = geneJson['claims']["P703"][0]["mainsnak"]["datavalue"]["value"]["id"]
    statements.append(wdi_core.WDItemID(taxonQID, prop_nr="P703", references=[copy.deepcopy(ncbi_reference)]))

    # refseq
    statements.append(wdi_core.WDString(refseqID, prop_nr="P637", references=[copy.deepcopy(ncbi_reference)]))

    handle = Entrez.efetch(id=geneinfo["refseq"]["protein"], db='protein', rettype='gb', retmode='text')
    record = SeqIO.read(handle, 'genbank')
    for feature in record.features:
        if feature.type.lower() == "protein":
            print(feature.qualifiers['product'])
            protein_label = feature.qualifiers['product'][0]
    taxonname = getTaxonItem(geneJson['claims']["P703"][0]["mainsnak"]["datavalue"]["value"]["id"]).get_label(lang="en")

    protein_item = wdi_core.WDItemEngine(data=statements)
    if protein_item.get_label(lang="en") == "":
        protein_item.set_label(protein_label, lang="en")
    if protein_item.get_description(lang="en") == "":
        protein_item.set_description("protein in " + taxonname, lang="en")
    if protein_item.get_description(lang="de") == "":
        protein_item.set_description("Eiweiß in " + taxonname, lang="de")
    if protein_item.get_description(lang="nl") == "":
        protein_item.set_description("eiwit in " + taxonname, lang="nl")
    if protein_item.get_description(lang="es") == "":
        protein_item.set_description("proteína en " + taxonname, lang="es")
    if protein_item.get_description(lang="it") == "":
        protein_item.set_description("Proteina in " + taxonname, lang="it")

    pprint.pprint(protein_item.get_wd_json_representation())
    protein_qid = protein_item.write(login)
    print(protein_qid)

    ## add the newly create protein item to the gene item
    encodes = [wdi_core.WDItemID(protein_qid, prop_nr="P688", references=[copy.deepcopy(ncbi_reference)])]
    geneitem = wdi_core.WDItemEngine(wd_item_id=geneqid, data=encodes)
    return geneitem.write(login)



"""## Start of the code
### Authentication
Username and password can be set at the beginning of this document for the authentication with WikiData.
"""

## Login to Wikidata
print("Logging in...")
if "WDUSER" in os.environ and "WDPASS" in os.environ:
  WDUSER = os.environ['WDUSER']
  WDPASS = os.environ['WDPASS']
else:
  raise ValueError("WDUSER and WDPASS must be specified in local.py or as environment variables")

"""### NCBI Taxon identifier
The genes and proteins that are to be registered in WikiData are selected based on the taxon identifier provided.
"""

taxids = ["694009", "1335626", "277944", "11137", "290028", "31631", "2697049"] # "NCBI Taxon number here. For example: 694009"

retrieved = datetime.now()
login = wdi_login.WDLogin(WDUSER, WDPASS)


for taxid in taxids:
    """## Creating the taxon instance"""

    item = set_taxon(taxid)
    wd_taxid = item.wd_item_id

    # Obtain scientific name

    for statement in item.statements:
        if statement.get_prop_nr() == "P225":
            scientificName = statement.value

    """### Acquiring genes
    Based on the taxon id provided this section will acquire the genes from mygene.info
    """

    # Obtain gene list from mygene.info
    genelist = json.loads(requests.get("https://mygene.info/v3/query?q=*&species=" + taxid).text)
    # pprint.pprint(genelist)
    for hit in genelist["hits"]:
        ncbi_reference = createNCBIGeneReference(hit["entrezgene"], retrieved)
        geneinfo = json.loads(requests.get("http://mygene.info/v3/gene/" + hit["entrezgene"]).text)
        statements = []

        ## P31 intance of
        statements.append(
            wdi_core.WDItemID("Q7187", prop_nr="P31", references=[copy.deepcopy(ncbi_reference)]))

        ## P703 found in taxon
        statements.append(wdi_core.WDItemID(wd_taxid, prop_nr="P703", references=[copy.deepcopy(ncbi_reference)]))

        # ncbi identifer
        statements.append(
            wdi_core.WDString(geneinfo["entrezgene"], prop_nr="P351", references=[copy.deepcopy(ncbi_reference)]))

        item = wdi_core.WDItemEngine(data=statements)
        # print(item.wd_item_id)
        item.set_label(geneinfo["name"], lang="en")
        item.set_description(scientificName + " gene", lang="en")

        pprint.pprint(item.get_wd_json_representation()) ## get json for test purposes
        print(item.write(login))  # write the wikidata item and return the QID

    """### Acquiring protein information
    Functions needed to acquire the protein information
    """
    """## Protein run script"""

    for hit in genelist["hits"]:
        print(hit["entrezgene"])
        geneinfo = json.loads(requests.get("http://mygene.info/v3/gene/" + hit["entrezgene"]).text)
        # uniprot identifer
        if "uniprot" in geneinfo.keys():
            if "Swiss-Prot" in geneinfo["uniprot"]:
                if isinstance(geneinfo["uniprot"]["Swiss-Prot"], list):
                    for uniprot in geneinfo["uniprot"]["Swiss-Prot"]:
                        print(uniprot +": "+create_or_update_uniprot_protein_item(hit["entrezgene"], uniprot))
                else:
                    print(geneinfo["uniprot"]["Swiss-Prot"] +": "+create_or_update_uniprot_protein_item(hit["entrezgene"], geneinfo["uniprot"]["Swiss-Prot"]))
        elif "refseq" in geneinfo.keys():
            if "protein" in geneinfo["refseq"].keys():
                if isinstance(geneinfo["refseq"]["protein"], list):
                    for refseqID in geneinfo["refseq"]["protein"]:
                        try:
                           print(create_or_update_refseq_protein_item(hit["entrezgene"], refseqID))
                        except:
                            pass
                else:
                    try:
                        print(create_or_update_refseq_protein_item(hit["entrezgene"], geneinfo["refseq"]["protein"]))
                    except:
                        pass