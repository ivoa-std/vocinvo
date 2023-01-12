#!/usr/bin/python
"""
A validator for IVOA vocabularies according to 
http://ivoa.net/documents/Vocabularies.

You can run this without an argument, in which case it will validate
all IVOA vocabularies it finds on the vocabulary repo, or with an argument,
in which case it will try to find a deplayed IVOA vocabulary at that
place.

Dependencies (Debian notation): python3-requests, python3-rdflib

Distributed under CC-0 by the IVOA semantics working group.
"""

import io
import requests
from configparser import ConfigParser

import rdflib


IVOA_BASEURI = "http://www.ivoa.net/rdf/"
VOCABS_CONF_URI = ("https://raw.githubusercontent.com"
    "/ivoa-std/Vocabularies/master/vocabs.conf")


RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")


class Vocabulary:
    """A vocabulary to be validated.

    It is constructed with a vocabulary URI and exposes the
    uri and desise attributes; desise has the json-decoded desise.
    """
    def __init__(self, uri:str):
        self.uri = uri
        self.desise = requests.get(self.uri,
            headers={"accept": "application/x-desise+json"}).json()


# ------------------------------------------------------------------
# "the concept URI MUST begin with \url{http://www.ivoa.net/rdf}"
# -- I don't see how this could get wrong, but it's not hard to
# validate, so let's just do it

def assert_uri_form(vocab:Vocabulary):
    assert vocab.uri.startswith("http://www.ivoa.net/rdf/"
        ), ("Vocabuly URI does not point to the IVOA vocabulary repo"
        " (note that you can *retrieve* from https, but you cannot"
        " reference the https version)")


# ------------------------------------------------------------------
# "IVOA vocabularies MUST be based on W3C's Resource Description
# Framework."
# -- I suppose this could be operationalised as "see that
# our Turtle and RDF/X files properly parse and give a standard few
# triples (see below).  For anything deeper I'd point to "wait until
# something breaks" unless you have good ideas.


def assert_usable_turtle(vocab:Vocabulary):
    """raises when the turtle returned for vocab_uri is seriously broken.
    """
    turtle_source = requests.get(vocab.uri,
        headers={"accept": "text/turtle"}).text
    assert turtle_source.strip().startswith(f"@base <{vocab.uri}>."
        ), "Turtle source does not declare the right base URI"
    parsed = rdflib.Graph().parse(data=turtle_source, format="n3")

    # now let's see if we have all the labels that are in desise
    ns = rdflib.Namespace(vocab.uri+"#")
    label = RDFS.label
    for ident, props in vocab.desise["terms"].items():
        ltrips = list(parsed.triples((ns[ident], label, None)))
        assert len(ltrips)==1, f"{ident} has not exactly one label"


def assert_usable_rdfx(vocab:Vocabulary):
    """raises when the RDF/X returned for vocab_uri is seriously broken.
    """
    rdf_source = requests.get(vocab.uri,
        headers={"accept": "application/rdf+xml"}).text
    parsed = rdflib.Graph().parse(data=rdf_source, format="xml")

    # now let's see if we have all the labels that are in desise
    ns = rdflib.Namespace(vocab.uri+"#")
    label = RDFS.label
    for ident, props in vocab.desise["terms"].items():
        ltrips = list(parsed.triples((ns[ident], label, None)))
        assert len(ltrips)==1, f"{ident} has not exactly one label"


# ------------------------------------------------------------------
# "In IVOA vocabularies, this fragment identifier MUST consist of
# ASCII letters, numbers, underscores and dashes exclusively"

def assert_identifier_form(vocab:Vocabulary):
    required_form = re.compile("[a-zA-Z0-9_-]+$")
    for ident in vocab.desise["terms"]:
        assert required_form.match(ident), f"Identifier {ident} malformed."


class Reporter:
    """a facade for reporting validation problems.

    For now, we basically just print diagnostics, the only trick being
    that we group messages for the same vocabulary.
    """
    def __init__(self):
        self.cur_vocab = None
   
    def _message(self, severity:str, vocab_uri:str, message:str):
        if vocab_uri!=self.cur_vocab:
            print(f"\n>>> {vocab_uri}")
            self.cur_vocab = vocab_uri
        print(f"{severity} {message}")

    def error(self, vocab_uri:str, message:str):
        self._message("ERROR", vocab_uri, message)

    def warning(self, vocab_uri:str, message:str):
        self._message("warning", vocab_uri, message)

    def run_check(self, vocab:Vocabulary, check:callable):
        try:
            check(vocab)
        except Exception as msg:
            self.error(vocab.uri, msg)


def iter_vocabulary_uris():
    """returns the URIs of all vocabularies listed in the IVOA vocabulary
    repository.

    There is no proper API for that; we hence pull the vocabs.conf
    from the IVOA github repo and compute the URIs from there.
    """
    parser = ConfigParser()
    voc_config = parser.read_file(
        io.StringIO(
            requests.get(VOCABS_CONF_URI).text))

    for sect in parser:
        if sect=="DEFAULT":
            continue
        yield IVOA_BASEURI+parser[sect].get("path", sect)



def validate_vocabulary(vocab:Vocabulary, reporter:Reporter):
    """validates a single IVOA vocabulary, referenced by its URI.
    """
    reporter.run_check(vocab, assert_uri_form)
    reporter.run_check(vocab, assert_usable_turtle)
    reporter.run_check(vocab, assert_usable_rdfx)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate IVOA semantic resources")
    parser.add_argument("vocuris", metavar="URL", type=str, nargs="*",
        help="URI(s) of the vocabularies to validate.  Leave out to validate"
        " all vocabularies in the IVOA repo.")
    return parser.parse_args()


def main():
    args = parse_args()
    reporter = Reporter()

    if not args.vocuris:
        args.vocuris = list(iter_vocabulary_uris())
    
    for vocab_uri in args.vocuris:
        validate_vocabulary(Vocabulary(vocab_uri), reporter)


if __name__=="__main__":
    main()

# vim:et:sta:sw=4

