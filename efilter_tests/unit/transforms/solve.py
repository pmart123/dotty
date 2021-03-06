# EFILTER Forensic Query Language
#
# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
EFILTER test suite.
"""

__author__ = "Adam Sindelar <adamsh@google.com>"

from efilter import api
from efilter import ast
from efilter import errors
from efilter import query as q

from efilter.protocols import reducer
from efilter.protocols import repeated

from efilter.transforms import solve

from efilter_tests import mocks
from efilter_tests import testlib


# Pylint gets confused about nested tuples in the lisp examples below.
# pylint: disable=bad-continuation

class SolveTest(testlib.EfilterTestCase):
    def testQuery(self):
        """Get coverage test to shut up."""
        pass

    def testLiteral(self):
        self.assertEqual(
            solve.solve(q.Query("42"), {}).value,
            42)

    def testVar(self):
        self.assertEqual(
            solve.solve(q.Query("foo"), {"foo": "bar"}).value,
            "bar")

    def testApply(self):
        self.assertEqual(
            solve.solve(
                q.Query("multiply(x: 5, y: 5)"),
                dict(multiply=mocks.MockFunction())).value,
            25)

        with self.assertRaises(errors.EfilterError):
            solve.solve(
                q.Query("multiply(x: 5, 'y': 5)"),
                dict(multiply=lambda x, y: x * y))

    def testBind(self):
        query = q.Query("bind('x': 5, 'y': 10)")

        self.assertEqual(
            solve.solve(query, {}).value,
            {"x": 5, "y": 10})

    def testSubselects(self):
        query = q.Query(
            "5 + SELECT age FROM"
            " (bind('age': 10, 'name': 'Tom'), bind('age': 8, 'name': 'Jerry'))"
            " WHERE name == 'Jerry'")
        self.assertEqual(
            solve.solve(query, {}).value,
            13)

        # This should fail because we're selecting two values.
        query = q.Query(
            "5 + SELECT age, name FROM"
            " (bind('age': 10, 'name': 'Tom'), bind('age': 8, 'name': 'Jerry'))"
            " WHERE name == 'Jerry'")
        with self.assertRaises(errors.EfilterTypeError):
            solve.solve(query, {})

        # Returning multiple results from SELECT should work with set
        # operations.
        query = q.Query(
            "let users = ("
            " bind('age': 10, 'name': 'Tom'),"
            " bind('age': 8, 'name': 'Jerry')"
            "),"
            "names = SELECT name FROM users"
            " SELECT * FROM users WHERE name IN names")

        self.assertValuesEqual(
            solve.solve(query, {}).value,
            repeated.meld({"age": 10, "name": "Tom"},
                          {"age": 8, "name": "Jerry"}))

        # However, equivalence should blow up:
        query = q.Query(
            "let users = ("
            " bind('age': 10, 'name': 'Tom'),"
            " bind('age': 8, 'name': 'Jerry')"
            "),"
            "names = SELECT name FROM users"
            " SELECT * FROM users WHERE name == names")

        with self.assertRaises(errors.EfilterTypeError):
            # Need to force the results to be realized (solve is lazy), hence
            # the list.
            list(solve.solve(query, {}).value)

        # It also shouldn't work if the subselect returns multiple columns.
         # However, equivalence should blow up:
        query = q.Query(
            "let users = ("
            " bind('age': 10, 'name': 'Tom'),"
            " bind('age': 8, 'name': 'Jerry')"
            "),"
            "names = SELECT * FROM users"
            " SELECT * FROM users WHERE name IN names")

        with self.assertRaises(errors.EfilterTypeError):
            # Need to force the results to be realized (solve is lazy), hence
            # the list.
            list(solve.solve(query, {}).value)

    def testRepeat(self):
        query = q.Query("(1, 2, 3, 4)")
        self.assertEqual(
            solve.solve(query, {}).value,
            repeated.meld(1, 2, 3, 4))

        # Repeated values flatten automatically.
        query = q.Query("(1, (2, 3), 4)")
        self.assertEqual(
            solve.solve(query, {}).value,
            repeated.meld(1, 2, 3, 4))

        # Expressions work.
        query = q.Query("(1, (2 + 2), 3, 4)")
        self.assertEqual(
            solve.solve(query, {}).value,
            repeated.meld(1, 4, 3, 4))

        # Repeated values are mono-types.
        with self.assertRaises(errors.EfilterTypeError):
            query = q.Query("(1, 'foo', 3, 4)")
            solve.solve(query, {})

    def testTuple(self):
        query = q.Query("[1, 2, 3]")
        self.assertEqual(
            solve.solve(query, {}).value,
            (1, 2, 3))

        query = q.Query("[x + 5, 1 == 1, y['foo']]")
        self.assertEqual(
            solve.solve(query, {"x": 2, "y": {"foo": "bar"}}).value,
            (7, True, "bar"))

    def testIfElse(self):
        query = q.Query(("if", True, "foo", "bar"))
        self.assertEqual(
            solve.solve(query, {}).value,
            "foo")

        query = q.Query(("if", False, "foo", False, "baz", "bar"))
        self.assertEqual(
            solve.solve(query, {}).value,
            "bar")

    def testPair(self):
        query = q.Query("false or x: y")
        self.assertEqual(
            solve.solve(query, dict(x="foo", y="bar")).value,
            ("foo", "bar"))

    def testReverse(self):
        query = q.Query(
            ast.Apply(
                ast.Var("reverse"),
                ast.Repeat(
                    ast.Literal(1),
                    ast.Literal(2),
                    ast.Literal(3))))
        self.assertEqual(
            solve.solve(query, {}).value,
            repeated.meld(3, 2, 1))

    def testCount(self):
        query = q.Query("count((x, y, z))")
        self.assertEqual(solve.solve(query, dict(x=1, y=2, z=3)).value, 3)

    def testMap(self):
        self.assertEqual(
            solve.solve(
                q.Query("foo.bar"), {"foo": {"bar": "baz"}}).value,
            "baz")

    def testLet(self):
        self.assertEqual(
            solve.solve(
                ast.Let(
                    ast.Bind(
                        ast.Pair(
                            ast.Literal("x"),
                            ast.Literal(5))),
                    ast.Sum(
                        ast.Var("x"),
                        ast.Var("x"))),
                {}).value,
            10)

        # Previous binding should be made available to subsequent bindings.
        self.assertEqual(
            solve.solve(
                ast.Let(
                    ast.Bind(
                        ast.Pair(
                            ast.Literal("x"),
                            ast.Literal(5)),
                        ast.Pair(
                            ast.Literal("y"),
                            ast.Sum(
                                ast.Var("x"),
                                ast.Literal(5)))),
                    ast.Var("y")),
                {}).value,
            10)

    def testSelect(self):
        self.assertEqual(
            solve.solve(q.Query("x['y']"),
                        {"x": {"y": 5}}).value,
            5)

    def testResolve(self):
        self.assertEqual(
            solve.solve(q.Query("x.y"),
                        {"x": {"y": 5}}).value,
            5)

        self.assertEqual(
            solve.solve(q.Query("x.y.z"),
                        {"x": {"y": {"z": 5}}}).value,
            5)

    def testEach(self):
        self.assertFalse(
            solve.solve(
                q.Query("each(Process.parent, (pid == 1))"),
                {"Process": {"parent": repeated.meld(
                    mocks.Process(1, None, None),
                    mocks.Process(2, None, None))}}).value)

    def testAny(self):
        self.assertTrue(
            solve.solve(
                q.Query("any Process.parent where (pid == 1)"),
                {"Process": {"parent": repeated.meld(
                    mocks.Process(1, None, None),
                    mocks.Process(2, None, None))}}).value)

        # Test that unary ANY works as expected.
        query = q.Query(ast.Any(ast.Var("x")))
        self.assertFalse(solve.solve(query, {"x": None}).value)
        self.assertTrue(solve.solve(query, {"x": 1}).value)
        self.assertTrue(solve.solve(query, {"x": repeated.meld(1, 2, 3)}).value)

    def testSort(self):
        self.assertEqual(
            solve.solve(
                q.Query("select * from Process order by pid"),
                {"Process": repeated.meld(
                    mocks.Process(2, None, None),
                    mocks.Process(1, None, None))}).value,
            repeated.meld(
                mocks.Process(1, None, None),
                mocks.Process(2, None, None)))

        # How about nested repeated fields? This should sort the process
        # children and return those.
        self.assertEqual(
            solve.solve(
                q.Query("select * from Process.children order by pid"),
                {"Process": {"children": repeated.meld(
                    mocks.Process(2, None, None),
                    mocks.Process(1, None, None))}}).value,
            repeated.meld(
                mocks.Process(1, None, None),
                mocks.Process(2, None, None)))

        # Sorting BY a repeated expression should be the same as sorting by
        # a tuple.
        self.assertValuesEqual(
            solve.solve(
                q.Query("select name, surname from people order by "
                        "[lower(surname), lower(name)]"),
                {
                    "people": [
                        {"name": "John", "surname": "Smith"},
                        {"name": "John", "surname": "Brown"},
                        {"name": "John", "surname": "Lennon"},
                        {"name": "Alice", "surname": "Brown"},
                    ]
                }
            ).value,
            repeated.meld(
                {"name": "Alice", "surname": "Brown"},
                {"name": "John", "surname": "Brown"},
                {"name": "John", "surname": "Lennon"},
                {"name": "John", "surname": "Smith"},
            )
        )

        self.assertValuesEqual(
            solve.solve(
                q.Query("select name, surname from people order by "
                        "(lower(surname), lower(name))"),
                {
                    "people": [
                        {"name": "John", "surname": "Smith"},
                        {"name": "John", "surname": "Brown"},
                        {"name": "John", "surname": "Lennon"},
                        {"name": "Alice", "surname": "Brown"},
                    ]
                }
            ).value,
            repeated.meld(
                {"name": "Alice", "surname": "Brown"},
                {"name": "John", "surname": "Brown"},
                {"name": "John", "surname": "Lennon"},
                {"name": "John", "surname": "Smith"},
            )
        )

    def testFilter(self):
        self.assertValuesEqual(
            solve.solve(
                q.Query("select * from Process where (pid == 1)"),
                {"Process": repeated.meld(
                    mocks.Process(2, None, None),
                    mocks.Process(1, None, None))}).value,
            mocks.Process(1, None, None))

    def testReducer(self):
        # This should return a reducer that computes the mean of the age
        # property on a repeated object (tests let us use a dict as a stand-in).
        r = api.apply(("reducer", ("var", "mean"), ("var", "age")))
        self.assertIsInstance(r, reducer.IReducer)
        users = repeated.meld({"name": "Mary", "age": 10},
                              {"name": "Bob", "age": 20})
        average = reducer.reduce(r, users)
        self.assertEqual(average, 15)

    def testGroup(self):
        result = api.apply(
            query=q.Query(
                ("group",
                    # The input:
                    ("apply",
                        ("var", "csv"),
                        ("param", 0),
                        True),
                    # The grouper expression:
                    ("var", "country"),

                    # The output reducers:
                    ("reducer",
                        ("var", "singleton"),
                        ("var", "country")),
                    ("reducer",
                        ("var", "mean"),
                        ("cast",
                            ("var", "age"),
                            ("var", "int"))),
                    ("reducer",
                        ("var", "sum"),
                        ("cast",
                            ("var", "age"),
                            ("var", "int")))),
                params=[testlib.get_fixture_path("fake_users.csv")]),
            allow_io=True)

        # Round the output means for comparison.
        actual = []
        for row in result:
            row[1] = int(row[1])
            actual.append(row)

        expected = repeated.meld(['El Salvador', 55, 1287],
                                 ['Ethiopia', 55, 1210],
                                 ['French Guiana', 47, 381],
                                 ['Germany', 42, 299],
                                 ['Haiti', 46, 610],
                                 ['Mayotte', 50, 865],
                                 ['Portugal', 48, 485])

        self.assertItemsEqual(expected, actual)

    def testIsInstance(self):
        with self.assertRaises(
                errors.EfilterTypeError,
                error_f=lambda e: "Cannot find type named 'FooBar'" in str(e)):
            solve.solve(q.Query("proc isa FooBar"), mocks.MockRootType())

        self.assertTrue(solve.solve(q.Query("proc isa Process"),
                                    mocks.MockRootType()).value)

        # Builtin types should work, too.
        self.assertTrue(solve.solve(q.Query("5 isa int"), {}).value)

        # Always never forget to test for negatives.
        self.assertFalse(solve.solve(q.Query("5 isa str"), {}).value)

    def testCast(self):
        self.assertEqual(
            solve.solve(
                q.Query("cast(5, str)"),
                {}).value,
            "5")

    def testComplement(self):
        self.assertFalse(solve.solve(q.Query("not pid"),
                                     mocks.Process(1, None, None)).value)

    def testIntersection(self):
        self.assertFalse(solve.solve(q.Query("pid and not pid"),
                                     mocks.Process(1, None, None)).value)

    def testUnion(self):
        self.assertTrue(solve.solve(q.Query("pid or not pid"),
                                    mocks.Process(1, None, None)).value)

    def testSum(self):
        self.assertEqual(
            solve.solve(
                q.Query("pid + 10 + 20"),
                mocks.Process(1, None, None)).value,
            31)

    def testDifference(self):
        self.assertEqual(
            solve.solve(
                q.Query("(10 - pid) + 5"),
                mocks.Process(1, None, None)).value,
            14)

    def testProduct(self):
        self.assertEqual(
            solve.solve(
                q.Query("5 * 5 * 5"),
                mocks.Process(1, None, None)).value,
            125)

    def testQuotient(self):
        self.assertEqual(
            solve.solve(
                q.Query("10.0 / 4"),
                mocks.Process(1, None, None)).value,
            2.5)

    def testEquivalence(self):
        self.assertTrue(solve.solve(q.Query("pid == 1"),
                                    mocks.Process(1, None, None)).value)

    def testMembership(self):
        self.assertTrue(solve.solve(q.Query("pid in [1, 2]"),
                                    mocks.Process(1, None, None)).value)

        # Repeated should work, too.
        self.assertTrue(solve.solve(q.Query("pid in (1, 2)"),
                                    mocks.Process(1, None, None)).value)

        # Strings can be in strings.
        self.assertTrue(solve.solve(q.Query("'foo' in 'foobar'"), {}).value)

        # True negative.
        self.assertFalse(solve.solve(q.Query("'foo' in 'bar'"), {}).value)

        # This should also work for strings.
        self.assertTrue(solve.solve(q.Query("'foo' in 'foobar'"), {}).value)
        self.assertFalse(solve.solve(q.Query("'fzz' in 'foobar'"), {}).value)

        # Single characters.
        self.assertTrue(solve.solve(q.Query("'f' in 'foo'"), {}).value)

    def testRegexFilter(self):
        self.assertTrue(
            solve.solve(
                q.Query("name =~ 'ini.*'"),
                mocks.Process(1, "initd", None)).value)

    def testStrictOrderedSet(self):
        self.assertFalse(solve.solve(q.Query("pid > 2"),
                                     mocks.Process(1, None, None)).value)

    def testPartialOrderedSet(self):
        self.assertTrue(solve.solve(q.Query("pid >= 2"),
                                    mocks.Process(2, None, None)).value)

    def testMatchTrace(self):
        """Make sure that matching branch is recorded where applicable."""
        result = solve.solve(
            q.Query("pid == 1 or pid == 2 or pid == 3"),
            mocks.Process(2, None, None))

        self.assertEqual(
            q.Query(result.branch),
            q.Query("pid == 2"))

    def testDestructuring(self):
        result = solve.solve(
            q.Query("Process.pid == 1"), {"Process": {"pid": 1}})
        self.assertTrue(result.value)

        # Using a let-any form should succeed even if there is only one linked
        # object.
        result = solve.solve(
            q.Query("any Process.parent where (Process.pid == 1 or "
                    "Process.command == 'foo')"),
            {"Process": {"parent": {"Process": {"pid": 1}}}})
        self.assertTrue(result.value)
