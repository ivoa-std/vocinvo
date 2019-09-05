#!/usr/bin/python3
"""
This python module ("REad VOcabularies in the VO") is a small reference
implemenation pulling the central pieces of information from vocabularies
conforming to version 2 of the Vocabularies in the VO recommendation.

It can be used as a standalone so-so validator (it's not checking every
conceivable aspect), and it can be dropped into other software (and then
licensed as required there) and used as a library.

To run the embedded doctests, run the script without arguments.

This is written for python3 and has no dependencies beyond the standard
python library.

Written by Markus Demleitner <msdemlei@ari.uni-heidelberg.de> in 2019.

This code is in the public domain.
"""

import re
import sys
from urllib.request import Request, urlopen
from xml.etree import ElementTree


# A dict of namespace URIs to canonical prefixes -- we replace those
# on incoming items to have more readable code.
PREFIX_DEF = {
    "http://purl.org/dc/terms/": "dc",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/2004/02/skos/core#": "skos",
    "http://www.ivoa.net/rdf/ivoasem#": "ivoasem",
}


# The flavour-specific properties
PROPERTIES_BY_FLAVOUR = {
    "RDF Class": {
        "label_property": "rdfs:label",
        "description_property": "rdfs:comment",
        "wider_property": "rdfs:subClassOf",
    },
    "RDF Property": {
        "label_property": "rdfs:label",
        "description_property": "rdfs:comment",
        "wider_property": "rdfs:subPropertyOf",
    },
    "SKOS": {
        "label_property": "skos:prefLabel",
        "description_property": "skos:definition",
        "wider_property": "skos:broader",
    },
}

# Term types by flavour
TERM_TYPES = {
    "RDF Class": "rdfs:Class",
    "RDF Property": "rdf:Property",
    "SKOS": "skos:Concept",
}


def prefixify(etree_name):
    """returns a tag or attribute name with a canonical prefix (by
    PREFIX_DEF).
   
    etree_name is what's coming out of etree, i.e., simple strings,
    possibly of the form {ns-url}name.

    >>> prefixify("{http://purl.org/dc/terms/}foo")
    'dc:foo'
    >>> prefixify("{http://dc.g-vo.org}foo")
    '{http://dc.g-vo.org}foo'
    >>> prefixify("src")
    'src'
    """
    if etree_name.startswith('{'):
        mat = re.match("{([^}]+)}(.*)", str(etree_name))
        if mat and mat.group(1) in PREFIX_DEF:
            return "{}:{}".format(PREFIX_DEF[mat.group(1)], mat.group(2))
        # else fall through to return etree_name unchanged
    return etree_name


def prefixify_attrib(etree_attrib):
    """returns etree_attrib as a simple dictionary with keys from
    PREFIX_DEF namespaces having prefixes rather than URIs.
    """
    return dict(
        (prefixify(name), value)
        for name, value in etree_attrib.items())

def _make_url_prefixifier():
    """returns a function turning URLs with known prefixes into the
    prefix form.

    This should run in about linear time with the number of known
    namespaces; it will break when one ns URL is a prefix of another
    (which would be a terrible idea anyway).
    """
    prefix_re = re.compile(
        "({})(.*)".format("|".join(re.escape(u) for u in PREFIX_DEF)))

    def prefixify_url(url):
        """returns the prefix form of url if it starts with a known prefix.

        It will return url unchanged otherwise.

        >>> prefixify_url("http://purl.org/dc/terms/author")
        'dc:author'
        >>> prefixify_url("abc")
        'abc'
        """
        mat = prefix_re.match(url)
        if mat:
            return "{}:{}".format(PREFIX_DEF[mat.group(1)], mat.group(2))
        return url
    
    return prefixify_url

prefixify_url = _make_url_prefixifier()
del _make_url_prefixifier


class Vocabulary(object):
    """A facade for the major properties of VO vocabularies.

    This exposes:

    * terms -- a dictionary term -> (label, description).
    * deprecated_terms -- a dictionary mapping deprecated terms to a
      list of replacement terms.  An empty list indicates terms
      deprecated without replacement.
    * preliminary_terms -- a set of preliminary terms.
    * wider_terms -- a dictionary of term -> [wider terms] (where the
      length of the list must be 1 except for SKOS).
    * uri -- the vocabulary URI
    * flavour -- the kind of vocabulary; as of Vocinvo 2.0, this
      can be one of 'RDF Class', 'RDF Proprety' or 'SKOS'.

    * errors -- a list of strings naming errors encountered during parsing. 
      Clearly, this should be empty for a half-way reasonable vocabulary
      (but an empty errors list is not a sufficient condition for
      validity by the REC).

    It is likely that for actual use, you will want to derive some class
    with application-specific postprocessing.  The simplest way to achieve
    this is to override the postprocess method (that is a no-op in the
    default implementation, so there's no reason to up-call).

    You will usually construct these using the from_file class method;
    if you already have triples, feel free to construct them directly.
    In triples, all members must be written as CURIES ("rdfs:label") 
    if they are URIs starting with something in PREFIX_DEF (use
    prefixify_url if necessary).
    """
    # This is used by ValidatingVocabulary to influence parsing from files.
    _validating = False

    def __init__(self, triples):
        self.terms = {}
        self.deprecated_terms = {}
        self.preliminary_terms = set()
        self.wider_terms = {}
        self.errors = []
        self.uri = "Vocabulary URI not found in RDF/X"

        self._build_vocabulary(triples)
        self.postprocess()

    @classmethod
    def from_file(cls, fp):
        """returns a Vocabulary read from fp.

        fp must be an open file-like object containing RDF/XML.

        validating=True gives some extra semi-private attributes
        used by ValidatingVocabulary to the returned object.  Consider
        it undocumented for now.
        """
        triples = []
        elem_stack = [] # containing (name, attib) pairs with canonical
                        # prefixes.

        # to reduce the risk of confusing this with later extensions,
        # we only look at properties that we think we understand.
        # That's some basic ones, the ones from ivoasem, plus whatever 
        # we define in PROPERTIES_BY_FLAVOUR
        object_generating_elements = set()
        for _, propdef in PROPERTIES_BY_FLAVOUR.items():
            object_generating_elements |= set(propdef.values())
        object_generating_elements |= set([
            'rdf:type', 'rdf:about',
            'ivoasem:preliminary', 'ivoasem:deprecated', 'ivoasem:useInstead',
            'ivoasem:vocflavour',
            ]) 
        subject_generating_elements = set([
            "rdf:Property",
            "rdfs:Class",
            "skos:Concept",])

        if cls._validating:
            terms_from_typed_nodes = []

        for event, elem in ElementTree.iterparse(
                fp, events=["start", "end"]):
            if event=="start":
                elem_stack.append(
                    (prefixify(elem.tag), prefixify_attrib(elem.attrib)))
            else: # event=="end"
                tag_name, attrs = elem_stack.pop()
                if tag_name in object_generating_elements:
                    s = prefixify_url(elem_stack[-1][1]["rdf:about"])
                    # We probably should only prefixify rdf:resource
                    # values; but then, errors here are rather improbable.
                    o = prefixify_url(attrs.get("rdf:resource", elem.text))
                    triples.append((s, tag_name, o))

                if tag_name in subject_generating_elements:
                    s = prefixify_url(attrs["rdf:about"])
                    triples.append((
                        s,
                        'rdf:type',
                        tag_name))
                    # extra service for ValidatingVocabulary
                    if cls._validating:
                        terms_from_typed_nodes.append(s)

        if cls._validating:
            triples.append(
                (None, "debug:terms_from_typed_nodes", terms_from_typed_nodes))

        return cls(triples)

    def postprocess(self):
        """called when all triples are digested.

        To be overridden by subclasses.  The default implemenation is a
        no-op.
        """
        pass

    def to_term(self, uri):
        """returns the term (the thing behind the #) if uri is in this
        vocabulary's namespace, the full uri otherwise.
        """
        if uri.startswith(self.uri):
            return uri[len(self.uri)+1:]
        return uri

    ############## only constructor helpers beyond this point

    def _add_error(self, error_string):
        """adds an error message.

        A constructor helper, not for users.
        """
        self.errors.append(error_string)

    def _get_vocab_uri(self, by_property):
        """sets the vocabulary URI.

        A constructor helper, not for users.
        """
        pairs = by_property.get('ivoasem:vocflavour')

        if not pairs:
            self._add_error("No ivoasem:vocflavour declared.  Is this"
                " an IVOA vocabulary?")
            return
        if len(pairs)>1:
            self._add_error("More than one ivoasem:vocflavour clause"
                " found.  Picking one at random.  This is going to"
                " be trouble.")

        self.uri = pairs[0][0]
        self.flavour = pairs[0][1]

        if self.flavour not in PROPERTIES_BY_FLAVOUR:
            self._add_error("Flavour {} unknown.  This must be one of {}."
                .format(self.flavour, ", ".join(PROPERTIES_BY_FLAVOUR)))

        for key, value in PROPERTIES_BY_FLAVOUR[self.flavour].items():
            setattr(self, key, value)

        self.term_type = TERM_TYPES[self.flavour]

    def _build_terms(self, by_property):
        """fills the terms attribute.

        A constructor helper, not for users.
        """
        labels = dict(by_property.get(self.label_property, []))
        definitions = dict(by_property.get(self.description_property, []))

        for s, o in by_property.get("rdf:type", []):
            if o==self.term_type and s.startswith(self.uri):
                self.terms[self.to_term(s)] = (
                    labels.get(s),
                    definitions.get(s))

    def _build_hierarchy(self, by_property):
        """fills the wider_terms attribute.

        A constructor helper, not for users.
        """
        for s, o in by_property.get(self.wider_property, []):
            if s.startswith(self.uri):
                self.wider_terms.setdefault(
                    self.to_term(s), []).append(self.to_term(o))

    def _build_deprecated_terms(self, by_property):
        """fills the wider_terms attribute.

        A constructor helper, not for users.
        """
        for s, o in by_property.get("ivoasem:deprecated", []):
            if s.startswith(self.uri):
                self.deprecated_terms[self.to_term(s)] = []

        for s, o in by_property.get("ivoasem:useInstead", []):
            if s.startswith(self.uri):
                try:
                    self.deprecated_terms[self.to_term(s)
                        ].append(self.to_term(o))
                except KeyError:
                    self.errors.append("UseInstead given for non-deprecated"
                        " term {}.  Ignoring.".format(self.to_term(s)))

    def _build_preliminary(self, by_property):
        """fills the preliminary_terms attribute.

        A constructor helper, not for users.
        """
        for s, _ in by_property.get("ivoasem:preliminary", []):
            if s.startswith(self.uri):
                self.preliminary_terms.add(self.to_term(s))
      
    def _build_vocabulary(self, triples):
        """builds the vocabulary from RDF triples.

        A constructor helper, not for users.  It just happens to
        return the by_property dict of triples (in property -> (subject, object)
        form) -- that's convenient for validation.
        """
        by_property = {}
        for s, p, o in triples:
            by_property.setdefault(p, []).append((s,o))

        self._get_vocab_uri(by_property)
        self._build_terms(by_property)
        self._build_hierarchy(by_property)
        self._build_deprecated_terms(by_property)
        self._build_preliminary(by_property)
        return by_property


class ValidatingVocabulary(Vocabulary):
    """A Vocabulary that performs a set of validating steps after loading.

    This adds a warnings attribute containing strings, each one corresponding
    to a different warning.
    """
    _validating = True

    def __init__(self, triples):
        self.warnings = []
        Vocabulary.__init__(self, triples)

    def _add_warning(self, message):
        self.warnings.append(message)

    def _build_vocabulary(self, triples):
        by_property = Vocabulary._build_vocabulary(self, triples)
        self._validate_clean_flavour(by_property)
        self._validate_term_form()
        self._validate_complete_terms(by_property)
        self._validate_suspicious_definitions(by_property)
        self._validate_typed_node_form(by_property)
        self._validate_vocabulary_uri()
        if self.flavour=="SKOS":
            self._validate_extra_skos_properties(by_property)
        if self.flavour in ["RDF Class", "RDF Property"]:
            self._validate_treelike()

    ############ various validators only below here

    def _validate_clean_flavour(self, by_property):
        """ensures only properties suitable for the declared flavour
        are being used.
        """
        skos_properties = ["skos:prefLabel", "skos:definition",
            "skos:broader",]
        forbidden_properties = {
            # we don't warn against rdfs:label and rdfs:comment in
            # SKOS because we use them for the vocabulary as a whole
            # (and they probably don't hurt).
            "SKOS": ['rdfs:subClassOf', 'rdfs:subPropertyOf'],
            "RDF Class": ['rdfs:subPropertyOf']+skos_properties,
            "RDF Property": ['rdfs:subClassOf']+skos_properties,}[self.flavour]

        for prop in forbidden_properties:
            for s, o in by_property.get(prop, []):
                self._add_warning("Forbidden triple in {} vocabularies:"
                    " {} {} {}".format(
                    self.flavour, s, prop, o))
        
        forbidden_term_types = {"rdfs:Class", "rdf:Property",
            "skos:Concept"}
        forbidden_term_types.remove(TERM_TYPES[self.flavour])

        for s, o in by_property.get("rdf:type", []):
            if o in forbidden_term_types:
                self._add_error("{} has type {}, which is forbidden in"
                    " {} vocabularies".format(s, o, self.flavour))
  
    def _validate_term_form(self):
        term_form = re.compile("[^A-Za-z0-9_-]+")
        for t in self.terms:
            mat = term_form.search(t)
            if mat: 
                self._add_error("IVOA terms can only contain ASCII letters,"
                    " digits, underscores, and dashes; {} has '{}'".format(
                    t, mat.group(0)))

    def _validate_complete_terms(self, by_property):
        for t, d in self.terms.items():
            if d[0] is None:
                self._add_error("Term {} has no label.".format(t))
            if d[1] is None:
                self._add_error("Term {} has no definition.".format(t))

    def _validate_suspicious_definitions(self, by_property):
        for t, d in self.terms.items():
            if d[0] and d[1] and (
                    d[0].lower() in d[1].lower()
                    or t.lower() in d[1].lower()):
                self._add_warning("Term {} repeats its label or fragment in"
                    " its definition.".format(t))

    def _validate_typed_node_form(self, by_property):
        _, terms_from_typed_nodes = by_property[
            "debug:terms_from_typed_nodes"][0]
        typed_node_missing = set(self.terms)-set(self.to_term(s) 
            for s in terms_from_typed_nodes)
        for t in typed_node_missing:
            self._add_error("Term {} not defined through a typed node".
                format(t))

    def _validate_vocabulary_uri(self):
        ivo_voc_uri = "http://www.ivoa.net/rdf/"
        if self.uri.startswith(ivo_voc_uri):
            if "/" in self.uri[len(ivo_voc_uri):]:
                self._add_warning("Vocabularies URIs should not introduce"
                    " additional hierarchy below w.i.n/rdf.")
        else:
            self._add_error("Vocabulary URI {} does not start with"
                " the canonical IVOA vocabulary URI root.".format(self.uri))

    def _validate_extra_skos_properties(self, by_property):
        frowned_upon = ["skos:related", "skos:exactMatch", "skos:closeMatch", 
            "skos:broadMatch", "skos:narrowMatch", "skos:ConceptScheme", 
            "skos:inScheme", "skos:hasTopconcept", "skos:altLabel", 
            "skos:hiddenLabel"]
        for prop in frowned_upon:
            if prop in by_property:
                self._add_warning("IVOA SKOS vocabularies should not use"
                    " the {} property for now (used here {} time(s)).".format(
                    prop, len(by_property[prop])))

    def _validate_treelike(self):
        for term, wider in self.wider_terms.items():
            if len(wider)>1:
                self._add_error("Terms in non-SKOS vocabularies may only"
                    " have up to one wider term, but {} has {}.".format(
                    term, ", ".join(wider)))

def load_vocabulary(voc_spec):
    """returns a Vocabulary instance for voc_spec.

    voc_spec is either a (http/https) URL or a path to a local file.
    """
    if re.match("https?://", voc_spec):
        req = Request(voc_spec, headers={"accept": "application/rdf+xml"})
        in_file = urlopen(req)
    else:
        in_file = open(voc_spec)

    try:
        return Vocabulary.from_file(in_file)
    finally:
        in_file.close()


def check_one(voc_spec):
    """reads a vocabulary and emits errors and properties about it on
    stdout.
    """
    voc = load_vocabulary(voc_spec)
    print("{} terms, e.g., {}".format(
        len(voc.terms), list(voc.terms.keys())[0] if voc.terms else "-"))


def _test():
    """runs some doctests (we've lazy with those).
    """
    import doctest
    doctest.testmod()


def main():
    if len(sys.argv)<2:
        _test()
        sys.exit("Usage: {} <voc-spec> {{<voc-spec>}}\nwhere <voc-spec>"
            " either references a local RDF/X file or the vocabulary"
            " URL.".format(sys.argv[0]))
  
    for voc_spec in sys.argv[1:]:
        print("\n=== Vocabulary {}".format(voc_spec))
        check_one(voc_spec)


if __name__=="__main__":
  main()

# vim:et:sta:sw=4
