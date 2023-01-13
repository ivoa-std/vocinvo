#!/usr/bin/python
"""
A validator for IVOA vocabularies according to 
http://ivoa.net/documents/Vocabularies.

You can run this without an argument, in which case it will validate
all IVOA vocabularies it finds on the vocabulary repo, or with an argument,
in which case it will try to find a deplayed IVOA vocabulary at that
place.

The actual tests are written below as assert_* functions, each accepting
a Vocabulary instance as its argument.  If a test fails, these should
raise a sufficiently expressive exception.  If you add tests, please follow
the existing practice of prepending them with the spec language it
attempts to verify.

All assert_ functions are automatically run by validate_vocabulary.

Dependencies (Debian notation): python3-requests, python3-rdflib

Distributed under CC-0 by the IVOA semantics working group.
"""

import functools
import io
import re
import requests
from configparser import ConfigParser

import rdflib


IVOA_BASEURI = "http://www.ivoa.net/rdf/"
VOCABS_CONF_URI = ("https://raw.githubusercontent.com"
    "/ivoa-std/Vocabularies/master/vocabs.conf")


DC = rdflib.Namespace("http://purl.org/dc/terms/")
IVOASEM = rdflib.Namespace("http://www.ivoa.net/rdf/ivoasem#")
RDFS = rdflib.Namespace("http://www.w3.org/2000/01/rdf-schema#")
SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")


class Vocabulary:
    """A vocabulary to be validated.

    It is constructed with a vocabulary URI and exposes the
    uri and desise attributes; desise has the json-decoded desise.

    Use vocab[term] to produce concept URIs for a vocabulary.
    """
    def __init__(self, uri:str):
        self.uri = uri
        self.desise = requests.get(self.uri,
            headers={"accept": "application/x-desise+json"}).json()
        self.ns = rdflib.Namespace(self.uri+"#")

    @functools.cache
    def get_rdfx(self):
        """returns an rdflib graph parsed from the RDF/X rendering.

        Use this for assertions only/best visible in full RDF (rather than
        desise).
        """
        rdf_source = requests.get(self.uri,
            headers={"accept": "application/rdf+xml"}).text
        return rdflib.Graph().parse(data=rdf_source, format="xml")


    def __getitem__(self, item):
        return self.ns[item]


################## Begin tests

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
    
    ns = rdflib.Namespace(vocab.uri+"#")
    for ident, props in vocab.desise["terms"].items():
        ltrips = list(parsed.triples((ns[ident], None, None)))
        assert len(ltrips)>1, f"{ident} missing in turtle"


def assert_usable_rdfx(vocab:Vocabulary):
    """raises when the RDF/X returned for vocab_uri is seriously broken.
    """
    parsed = vocab.get_rdfx()
    ns = rdflib.Namespace(vocab.uri+"#")

    for ident, props in vocab.desise["terms"].items():
        ltrips = list(parsed.triples((ns[ident], None, None)))
        assert len(ltrips)>1, f"{ident} missing in RDF/X"


# ------------------------------------------------------------------
# "In IVOA vocabularies, this fragment identifier MUST consist of
# ASCII letters, numbers, underscores and dashes exclusively"

def assert_identifier_form(vocab:Vocabulary):
    required_form = re.compile("[a-zA-Z0-9_-]+$")
    for ident in vocab.desise["terms"]:
        assert required_form.match(ident), f"Identifier {ident} malformed."


# ------------------------------------------------------------------
# "each vocabulary must be clearly identified as \emph{either} giving
# SKOS concepts..." -- that's a simple condition on ivoasem:vocflavour

def assert_vocflavour_given(vocab:Vocabulary):
    assert vocab.desise["flavour"] in {
        "RDF Class",
        "RDF Property",
        "SKOS"}
    flvs = list(vocab.get_rdfx().triples((None, IVOASEM.vocflavour, None)))
    assert len(flvs)==1
    assert str(flvs[0][-1])==vocab.desise["flavour"]


# ------------------------------------------------------------------
# [SKOS, RDF class/property]
# "all concepts MUST have an English-language preferred label" --
# "English-language" will probably not be reasonably validatable, "a
# non-empty string" is easy.

def assert_skos_preferred_label(vocab:Vocabulary):
    if vocab.desise["flavour"]=="SKOS":
        labelProp = SKOS.prefLabel
    else:
        labelProp = RDFS.label

    graph = vocab.get_rdfx()
    for term in vocab.desise["terms"]:
        labels = list(graph.triples(
            (vocab[term], labelProp, None)))
        assert len(labels)==1, (
            f"No (unique) preferred label on {term}: {labels}")
        assert str(labels[0][2]).strip()!="", f"Empty label on {term}"


# ------------------------------------------------------------------
# [SKOS]
# "all concepts MUST have a non-trivial English-language definition"
# -- again, "non-empty" would work.  There is a problem with the UAT
# here, because they still don't have proper descriptions for the
# majority of their concepts, and they certainly won't be complete
# for many years.  Let's see if I live with regular errors on that.

def assert_skos_definition(vocab:Vocabulary):
    if vocab.desise["flavour"]=="SKOS":
        defProp = SKOS.definition
    else:
        defProp = RDFS.comment

    graph = vocab.get_rdfx()
    for term in vocab.desise["terms"]:
        defs = list(graph.triples((vocab[term], defProp, None)))
        assert len(defs)==1, f"No (unique) definition on {term}: {defs}"
        assert str(defs[0][2]).strip()!="", f"Empty definition on {term}"


# ------------------------------------------------------------------
# [RDF class/property]
# "term MUST NOT appear as subject of more than one
# \vocterm{rdfs:subPropertyOf} triple" -- that's an interesting one,
# as it's trivial to validate in Desise, so if we trust the Desise
# tooling, that would be done.  With a bit more work, we could
# validate this from the RDF artefacts.  Can't say whether I'll do
# that.

def assert_tree_shape(vocab:Vocabulary):
    if not vocab.desise["flavour"].startswith("RDF "):
        return

    graph = vocab.get_rdfx()
    parentProp = RDFS.subPropertyOf
    for term in vocab.desise["terms"]:
        parents = list(graph.triples((vocab[term], parentProp, None)))
        assert len(parents)<2, f"{term} has more than one parent"


# ------------------------------------------------------------------
# "IVOA vocabularies MUST include exactly one triple with the
# vocabulary as subject and a predicate \vocterm{dc:created}" --
# straightforward, with the caveat on desise (that doesn't
# expose that info).

def assert_date_present(vocab:Vocabulary):
    graph = vocab.get_rdfx()
    created = list(graph.triples((None, DC.created, None)))
    assert len(created)==1, "No creation date."
    assert str(created[0][0])==vocab.uri, "Wrong subject on dc:created"
    assert re.match(r"2\d\d\d-\d\d-\d\d$", str(created[0][2])
        ), f"Odd creation date: {created[0][2]}"


# ------------------------------------------------------------------
# "\vocterm{ivoasem:useInstead} [...] This property MUST NOT be
# used with non-deprecated subjects." -- ah, that one could
# definitely go wrong at the moment.

def assert_use_instead_not_deprecated(vocab:Vocabulary):
    terms = vocab.desise["terms"]
    for ident, props in terms.items():
        if "useInstead" in props:
            assert props["useInstead"] in terms, (
                f"{ident} points to non-existing useInstead")
            assert "deprecated" not in terms[props["useInstead"]
                ], f"{ident} points to deprecated useInstead"


# ------------------------------------------------------------------
# "Each term in the IVOA vocabulary mirror MUST declare its identity to
# the original, external RDF resource." 
# -- VocInVO currently has no way to declare that a vocabulary is mirrored
# from somewhere.  The next version should have it, but meanwhile
# we record that information here.

MIRRORED_VOCS = {
    'http://www.ivoa.net/rdf/uat',
}

def assert_mirrored_voc_declares_sources(vocab:Vocabulary):
    if vocab.uri not in MIRRORED_VOCS:
        return
   
    graph = vocab.get_rdfx()
    for ident in vocab.desise["terms"]:
        assert list(graph.triples((vocab.ns[ident], SKOS.exactMatch, None))
            ), f"#{ident} has no upstream exactMatch although it is mirrored"
    

#################### End tests, infrastructure code only below


class Reporter:
    """a facade for reporting validation problems.

    For now, we basically just print diagnostics, the only trick being
    that we group messages for the same vocabulary.
    """
    def __init__(self, bail:bool):
        self.bail = bail
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
            return check(vocab)
        except Exception as msg:
            self.error(vocab.uri, check.__name__+": "+str(msg))
            if self.bail:
                raise


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
    ns = globals()
    for name, fct in ns.items():
        if name.startswith("assert_"):
            reporter.run_check(vocab, fct)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate IVOA semantic resources")
    parser.add_argument("--bail", dest="bail", action="store_true",
        help="Bail out and dump a traceback on the first validation"
        " error.")
    parser.add_argument("vocuris", metavar="URL", type=str, nargs="*",
        help="URI(s) of the vocabularies to validate.  Leave out to validate"
        " all vocabularies in the IVOA repo.")
    return parser.parse_args()


def main():
    args = parse_args()
    reporter = Reporter(args.bail)

    if not args.vocuris:
        args.vocuris = list(iter_vocabulary_uris())
    
    for vocab_uri in args.vocuris:
        try:
            vocab = Vocabulary(vocab_uri)
        except Exception as ex:
            reporter.error(vocab_uri,
                f"Vocabulary critically broken: {ex.__class__.__name__}: {ex}")
            continue

        validate_vocabulary(vocab, reporter)


if __name__=="__main__":
    main()

# vim:et:sta:sw=4

