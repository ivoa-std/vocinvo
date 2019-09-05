#!/usr/bin/python3

# This is a little test suite for the VO vocabulary handling software.
# For terms and conditions, see revovo.py

import itertools
import unittest
from io import StringIO

from revovo import ValidatingVocabulary, Vocabulary


_XML_GEN_TEMPLATE = """
<rdf:RDF 
    xmlns:dc="http://purl.org/dc/terms/" 
    xmlns:foaf="http://xmlns.com/foaf/0.1/" 
    xmlns:ivoasem="http://www.ivoa.net/rdf/ivoasem#" 
    xmlns:owl="http://www.w3.org/2002/07/owl#" 
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" 
    xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#" 
    xmlns:xsd="http://www.w3.org/2001/XMLSchema#" 
    xmlns:skos="http://www.w3.org/2004/02/skos/core#"
    xmlns="http://www.ivoa.net/rdf/test#">
  <rdf:Description rdf:nodeID="genid1">
    <foaf:name>Demleitner, M.</foaf:name>
  </rdf:Description>
  <rdf:Description rdf:about="http://www.ivoa.net/rdf/test">
    <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Ontology"/>
  </rdf:Description>
  <rdf:Description rdf:about="http://www.ivoa.net/rdf/test">
    <dc:created>2019-08-30</dc:created>
    <dc:creator rdf:nodeID="genid1"/>
    <rdfs:label>A (mostly broken) test vocabulary</rdfs:label>
    <dc:title>Test madness</dc:title>
    <dc:description>This is just for testing.</dc:description>
    {}
  </rdf:Description>
  {{}}
</rdf:RDF>
"""

XML_PROP_TEMPLATE = _XML_GEN_TEMPLATE.format(
    "<ivoasem:vocflavour>RDF Property</ivoasem:vocflavour>")

XML_CLASS_TEMPLATE = _XML_GEN_TEMPLATE.format(
    "<ivoasem:vocflavour>RDF Class</ivoasem:vocflavour>")

XML_SKOS_TEMPLATE = _XML_GEN_TEMPLATE.format(
    "<ivoasem:vocflavour>SKOS</ivoasem:vocflavour>")


# some triples to have some basic terms to play with in rdfs tests
COMMON_RDFS_TRIPLES = [
     ("tv:test", "rdfs:label", "My first term"),
     ("tv:test", "rdfs:comment", "No semantics attached"),
     ("tv:test", "ivoasem:deprecated", None),
     ("tv:test", "ivoasem:useInstead", "tv:second"),
     ("tv:second", "rdfs:label", "My second term"),
     ("tv:second", "rdfs:comment", "Means nothing either"),
     ("tv:stinky", "rdfs:label", "Old and boring"),
     ("tv:stinky", "rdfs:comment", "We shouldn't have done this."),
     ("tv:stinky", "ivoasem:deprecated", None),
     ("tv:experimental", "rdfs:label", "A proposed term"),
     ("tv:experimental", "rdfs:comment", "Under construction"),
     ("tv:experimental", "ivoasem:preliminary", None),
]


# some triples to have some basic terms to play with in skos tests
COMMON_SKOS_TRIPLES = [
     ("tv:stinky", "skos:broader", "tv:test"),
     ("tv:test", "skos:prefLabel", "My first term"),
     ("tv:test", "skos:definition", "No semantics attached"),
     ("tv:test", "ivoasem:deprecated", None),
     ("tv:test", "ivoasem:useInstead", "tv:second"),
     ("tv:second", "skos:prefLabel", "My second term"),
     ("tv:second", "skos:definition", "Means nothing either"),
     ("tv:stinky", "skos:prefLabel", "Old and boring"),
     ("tv:stinky", "skos:definition", 
         "We shouldn't have done this."),
     ("tv:stinky", "ivoasem:deprecated", None),
     ("tv:experimental", "skos:prefLabel", "A proposed term"),
     ("tv:experimental", "skos:definition", "Under construction"),
     ("tv:experimental", "ivoasem:preliminary", None),
     ("tv:experimental", "skos:broader", "tv:test"),
     ("tv:experimental", "skos:broader", "tv:second"),
]


def make_declarations(triples, term_class, 
        voc_uri="http://www.ivoa.net/rdf/test#"):
    """builds (in a very native way) RDF/XML declarations of the
    triples.

    We assume our standard prefixes.
    """
    res = []
    for s, triples_for_s in itertools.groupby(triples, lambda v: v[0]):
        if s is None:
            s = "tv:__"
        children = []
        for _, p, o in triples_for_s:
            if o is None:
                o = "tv:__"
            s = s.replace("tv:", voc_uri)
            o = o.replace("tv:", voc_uri)
            children.append(
                '  <{}>{}</{}>'.format(p, o, p))
        res.extend([
            '<{} rdf:about="{}">'.format(term_class, s),
            '\n  '.join(children),
            '</{}>'.format(term_class)])
    return "\n".join(res)


class LoadingTest(unittest.TestCase):

    def _assert_common(self, voc):
        # common assertions for the all flavours
        self.assertEqual(voc.uri, "http://www.ivoa.net/rdf/test")
        self.assertEqual(voc.terms["test"],
            ("My first term", "No semantics attached"))
        self.assertEqual(len(voc.terms), 4)
        self.assertEqual(voc.deprecated_terms["test"], ["second"])
        self.assertEqual(voc.deprecated_terms["stinky"], [])
        self.assertEqual(voc.preliminary_terms, set(["experimental"]))
        self.assertEqual(voc.wider_terms["stinky"], ["test"])
        self.assertEqual(voc.errors, [])

    def test_loading_prop(self):
        voc = Vocabulary.from_file(StringIO(
            XML_PROP_TEMPLATE.format(make_declarations([
                ("tv:stinky", "rdfs:subPropertyOf", "tv:test"),
            ]+COMMON_RDFS_TRIPLES, "rdf:Property"))))
        self.assertEqual(voc.flavour, "RDF Property")
        self._assert_common(voc)

    def test_loading_class(self):
        voc = Vocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations([
                ("tv:stinky", "rdfs:subClassOf", "tv:test"),
            ]+COMMON_RDFS_TRIPLES, "rdfs:Class"))))
        self.assertEqual(voc.flavour, "RDF Class")
        self._assert_common(voc)

    def test_loading_skos(self):
        voc = Vocabulary.from_file(StringIO(
            XML_SKOS_TEMPLATE.format(make_declarations(
                COMMON_SKOS_TRIPLES, "skos:Concept"))))
        self.assertEqual(voc.flavour, "SKOS")
        self.assertEqual(voc.wider_terms["experimental"],
            ["test", "second"])
        self._assert_common(voc)

    def test_loading_from_Description(self):
        voc = Vocabulary.from_file(StringIO(
            XML_PROP_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES, "rdf:Property")
            +'<rdf:Declaration'
            ' rdf:about="http://www.ivoa.net/rdf/test#stinky">'
            '<rdfs:subPropertyOf'
            ' rdf:resource="http://www.ivoa.net/rdf/test#test"/>'
            '</rdf:Declaration>')))
        self._assert_common(voc)


class ValidationTest(unittest.TestCase):
    def test_mixed_term_types_error(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_PROP_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES, "rdf:Property")
            +'<skos:Concept rdf:about="http://www.ivoa.net/rdf/test#extra">'
            '<skos:prefLabel>skos term</skos:prefLabel>'
            '<skos:definition>Must raise an error because it is skos'
            '</skos:definition>'
            '</skos:Concept>')))
        self.assertEqual(voc.errors,
            ['http://www.ivoa.net/rdf/test#extra has type skos:Concept, which'
                ' is forbidden in RDF Property vocabularies'])

    def test_skos_mixed_term_types_error(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_SKOS_TEMPLATE.format(make_declarations(
                COMMON_SKOS_TRIPLES, "skos:Concept")
            +'<rdf:Property rdf:about="http://www.ivoa.net/rdf/test#extra">'
            '<rdfs:label>skos term</rdfs:label>'
            '<rdfs:comment>Must raise an error because it is a property'
            '</rdfs:comment>'
            '</rdf:Property>'
            +'<rdfs:Class rdf:about="http://www.ivoa.net/rdf/test#cls">'
            '<rdfs:label>a class</rdfs:label>'
            '<rdfs:comment>Must raise an error because it is a class'
            '</rdfs:comment>'
            '</rdfs:Class>'
            )))
        self.assertEqual(set(voc.errors), {
            'http://www.ivoa.net/rdf/test#extra has type rdf:Property, which'
                ' is forbidden in SKOS vocabularies',
            'http://www.ivoa.net/rdf/test#cls has type rdfs:Class, which'
                ' is forbidden in SKOS vocabularies',})

    def test_forbidden_property_warnings(self):
        # the spec doesn't literally forbid rdfs:label (say) on SKOS stuff,
        # but it certainly is fishy if it's there.
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_PROP_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES+[
                    ("tv:test", "skos:broader", "tv:second"),
                    ("tv:stinky", "rdfs:subClassOf", "tv:experimental"),],
                "rdf:Property"))))
        self.assertEqual(set(voc.warnings), {
           'Forbidden triple in RDF Property vocabularies: http://www.ivoa.'
            'net/rdf/test#stinky rdfs:subClassOf http://www.ivoa.net/rdf/'
            'test#experimental',
           'Forbidden triple in RDF Property vocabularies: http://www.ivoa.'
            'net/rdf/test#test skos:broader http://www.ivoa.net/rdf/'
            'test#second',})

    def test_skos_forbidden_property_warnings(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_SKOS_TEMPLATE.format(make_declarations(
                COMMON_SKOS_TRIPLES+[
                    ('tv:test', 'rdfs:subPropertyOf', 'tv:stinky'),
                    ('tv:test', 'rdfs:subClassOf', 'tv:second')],
                "skos:Concept"))))
        self.assertEqual(set(voc.warnings), {
            'Forbidden triple in SKOS vocabularies:'
                ' http://www.ivoa.net/rdf/test#'
                'test rdfs:subClassOf http://www.ivoa.net/rdf/test#second',
            'Forbidden triple in SKOS vocabularies:'
                ' http://www.ivoa.net/rdf/test#'
                'test rdfs:subPropertyOf http://www.ivoa.net/rdf/test#stinky',
            })

    def test_incomplete_definition_errors(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES+[
                    ('tv:labelOnly', 'rdfs:label', 'Missing Def'),
                    ('tv:defOnly', 'rdfs:comment', 'Missing Label'),],
                'rdfs:Class'))))
        self.assertEqual(set(voc.errors), {
            'Term labelOnly has no definition.', 'Term defOnly has no label.'
            })

    def test_recursive_definition_warning(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES+[
                    ('tv:testCase', 'rdfs:label', 'Test Case'),
                    ('tv:testCase', 'rdfs:comment', 'A term used in'
                        ' a test case.'),],
                'rdfs:Class'))))
        self.assertEqual(voc.warnings, [
            'Term testCase repeats its label or fragment in its definition.'
            ])
            
    def test_no_typed_node_error(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES, 'rdfs:Class')
                +"""<rdf:Description 
                        rdf:about="http://www.ivoa.net/rdf/test#tech">
                    <rdf:type rdf:resource=
                        "http://www.w3.org/2000/01/rdf-schema#Class"/>
                    <rdfs:label>a label</rdfs:label>
                    <rdfs:comment>shut up the validator</rdfs:comment>
                </rdf:Description>"""
                # rdf:type Property is not an error as such in Class 
                # vocabularies (it's wrong because of type purity,
                # but that's a different error).
                +"""<rdf:Description rdf:about="http://www.ivoa.net/rdf/test#p">
                    <rdf:type rdf:resource=
                        "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"/>
                    <rdfs:label>another label</rdfs:label>
                    <rdfs:comment>shut up the validator again</rdfs:comment>
                </rdf:Description>"""
            )))
        self.assertEqual(set(voc.errors), {
            'http://www.ivoa.net/rdf/test#p has type rdf:Property,'
            ' which is forbidden in RDF Class vocabularies',
            'Term tech not defined through a typed node'})

    def test_non_ivoa_uri_errors(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES, 'rdfs:Class')).replace(
                "http://www.ivoa.net/rdf/test", "http://test.voc")))
        self.assertEqual(voc.errors, [
            "Vocabulary URI http://test.voc does not start with"
            " the canonical IVOA vocabulary URI root."])

    def test_uri_with_hierarchy_warnings(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES, 'rdfs:Class')).replace(
                "http://www.ivoa.net/rdf/test", 
                "http://www.ivoa.net/rdf/maint/test")))
        self.assertEqual(voc.warnings, [
            "Vocabularies URIs should not introduce"
                    " additional hierarchy below w.i.n/rdf."])

    def test_bad_term_name_errors(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES+[
                    ('tv:$ANYTHING', 'rdfs:label', 'wildcard'),
                    ('tv:$ANYTHING', 'rdfs:comment', 'This is invalid'),
                ], 'rdfs:Class'))))
        self.assertEqual(voc.errors, [
            "IVOA terms can only contain ASCII letters, digits, underscores,"
            " and dashes; $ANYTHING has '$'"])

    def test_nontree_errors(self):
        voc = ValidatingVocabulary.from_file(StringIO(
            XML_CLASS_TEMPLATE.format(make_declarations(
                COMMON_RDFS_TRIPLES+[
                    ('tv:test', 'rdfs:subClassOf', 'tv:second'),
                    ('tv:test', 'rdfs:subClassOf', 'tv:stinky'),
                ], 'rdfs:Class'))))
        self.assertEqual(voc.errors, [
            'Terms in non-SKOS vocabularies may only have up to one'
            ' wider term, but test has second, stinky.'])


def main():
    # for simpler development: you can pass two args
    # to only run specific tests from specific test cases.
    import os, sys
    if len(sys.argv)==3:
        className = sys.argv[1].split(".")[-1]
        testClass = getattr(sys.modules["__main__"], className)
        methodPrefix = sys.argv[2]
        suite = unittest.makeSuite(testClass, methodPrefix)
    else:  # emulate unittest.run behaviour
        suite = unittest.TestLoader().loadTestsFromModule(
        sys.modules["__main__"])

    runner = unittest.TextTestRunner(
        verbosity=int(os.environ.get("TEST_VERBOSITY", 1)))
    runner.run(suite)


if __name__=="__main__":
    main()

# vim:et:sta:sw=4
