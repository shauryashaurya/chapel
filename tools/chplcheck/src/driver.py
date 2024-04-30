#
# Copyright 2023-2024 Hewlett Packard Enterprise Development LP
# Other additional copyright holders may be indicated within.
#
# The entirety of this work is licensed under the Apache License,
# Version 2.0 (the "License"); you may not use this file except
# in compliance with the License.
#
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import functools
from typing import Any, Callable, Iterator, List, Optional, Tuple

import chapel
from fixits import Fixit
import rule_types

IgnoreAttr = ("chplcheck.ignore", ["rule", "comment"])


def ignores_rule(node: chapel.AstNode, rulename: str):
    """
    Given an AST node, check if it has an attribute telling it to silence
    warnings for a given rule.
    """

    ag = node.attribute_group()

    if ag is None:
        return False
    for attr in ag:
        attr_call = chapel.parse_attribute(attr, IgnoreAttr)
        if attr_call is None:
            continue

        ignored_rule = attr_call["rule"]
        if ignored_rule is not None and ignored_rule.value() == rulename:
            return True

    return False


class LintDriver:
    """
    Driver class containing the state and methods for linting. Among other
    things, contains the rules for emitting warnings, as well as the
    list of rules that should be silenced.

    Provides the @driver.basic_rule and @driver.advanced_rule decorators
    for registering new rules.
    """

    def __init__(self, skip_unstable: bool, internal_prefixes: List[str]):
        self.SilencedRules: List[str] = []
        self.BasicRules: List[Tuple[str, Any, rule_types.BasicRule]] = []
        self.AdvancedRules: List[Tuple[str, rule_types.AdvancedRule]] = []
        self.skip_unstable: bool = skip_unstable
        self.internal_prefixes: List[str] = internal_prefixes

    def rules_and_descriptions(self):
        # Use a dict in case a rule is registered multiple times.
        to_return = {}

        for rule in self.BasicRules:
            to_return[rule[0]] = rule[2].__doc__

        for rule in self.AdvancedRules:
            to_return[rule[0]] = rule[1].__doc__

        to_return = list(to_return.items())
        to_return.sort()
        return to_return

    def disable_rules(self, *rules: str):
        """
        Tell the driver to silence / skip warning for the given rules.
        """

        self.SilencedRules.extend(rules)

    def enable_rules(self, *rules: str):
        """
        Tell the driver to warn for the given rules even if they were
        previously disabled.
        """

        self.SilencedRules = list(set(self.SilencedRules) - set(rules))

    def _should_check_rule(
        self, rulename: str, node: Optional[chapel.AstNode] = None
    ):
        if rulename in self.SilencedRules:
            return False

        if node is not None and ignores_rule(node, rulename):
            return False

        return True

    def _has_internal_name(self, node: chapel.AstNode):
        if not hasattr(node, "name"):
            return False
        return any(node.name().startswith(p) for p in self.internal_prefixes)

    @staticmethod
    def _is_unstable_module(node: chapel.AstNode):
        if isinstance(node, chapel.Module):
            attrs = node.attribute_group()
            if attrs:
                if attrs.is_unstable():
                    return True
        return False

    @staticmethod
    def _in_unstable_module(node: chapel.AstNode):
        n = node
        while n is not None:
            if LintDriver._is_unstable_module(n):
                return True
            n = n.parent()
        return False

    def _preorder_skip_unstable_modules(self, node):
        if not self.skip_unstable:
            yield from chapel.preorder(node)
            return

        def recurse(node):
            if LintDriver._is_unstable_module(node):
                return

            yield node
            for child in node:
                yield from recurse(child)

        yield from recurse(node)

    def _check_basic_rule(
        self,
        context: chapel.Context,
        root: chapel.AstNode,
        rule: Tuple[str, Any, rule_types.BasicRule],
    ) -> Iterator[Tuple[chapel.AstNode, str, Optional[List[Fixit]]]]:
        (name, nodetype, func) = rule

        # If we should ignore the rule no matter the node, no reason to run
        # a traversal and match the pattern.
        if not self._should_check_rule(name):
            return

        for node, _ in chapel.each_matching(
            root, nodetype, iterator=self._preorder_skip_unstable_modules
        ):
            if not self._should_check_rule(name, node):
                continue

            val = func(context, node)
            check, fixit = None, []
            if isinstance(val, rule_types.BasicRuleResult):
                check = False
                fixit = val.fixits(context, name)
            else:
                check = val
            if not check:
                yield (node, name, fixit)

    def _check_advanced_rule(
        self,
        context: chapel.Context,
        root: chapel.AstNode,
        rule: Tuple[str, rule_types.AdvancedRule],
    ) -> Iterator[Tuple[chapel.AstNode, str, Optional[List[Fixit]]]]:
        (name, func) = rule

        # If we should ignore the rule no matter the node, no reason to run
        # a traversal and match the pattern.
        if not self._should_check_rule(name):
            return

        for result in func(context, root):
            if isinstance(result, rule_types.AdvancedRuleResult):
                node, anchor = result.node, result.anchor
                fixits = result.fixits(context, name)
                if anchor is not None and not self._should_check_rule(
                    name, anchor
                ):
                    continue
            else:
                node = result
                fixits = None

            # For advanced rules, the traversal of the AST is out of our hands,
            # so we can't stop it from going into unstable modules. Instead,
            # once the rule emits a warning, check by traversing the AST
            # if the warning target should be skipped.
            if self.skip_unstable and LintDriver._in_unstable_module(node):
                continue

            yield (node, name, fixits)

    def basic_rule(self, pat, default=True):
        """
        This method is a decorator factory for adding 'basic' rules to the
        driver. A basic rule is a function returning a boolean that gets called
        on any node that matches a pattern. If the function returns 'True', the
        node is good, and no warning is emitted. However, if the function returns
        'False', the node violates the rule.

        The name of the decorated function is used as the name of the rule.
        """

        def decorator_basic_rule(func):
            self.BasicRules.append((func.__name__, pat, func))
            if not default:
                self.SilencedRules.append(func.__name__)

            @functools.wraps(func)
            def wrapper_basic_rule(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper_basic_rule

        return decorator_basic_rule

    def advanced_rule(self, _func=None, *, default=True):
        """
        This method is a decorator for adding 'advanced' rules to the driver.
        An advanced rule is a function that gets called on a root AST node,
        and is expected to traverse that AST to find places where warnings
        need to be emitted.

        Advanced rules should yield either the node to be warned for, or
        a tuple of (node, anchor). The anchor is checked for silencing,
        making it possible to support @chplcheck.ignore for the advanced rule.

        The name of the decorated function is used as the name of the rule.
        """

        def decorator_advanced_rule(func):
            self.AdvancedRules.append((func.__name__, func))
            if not default:
                self.SilencedRules.append(func.__name__)

            @functools.wraps(func)
            def wrapper_advanced_rule(*args, **kwargs):
                return func(*args, **kwargs)

            return wrapper_advanced_rule

        # this allows the usage of either `@advanced_rule` or `@advanced_rule()`
        if _func is None:
            return decorator_advanced_rule
        else:
            return decorator_advanced_rule(_func)

    def run_checks(
        self, context: chapel.Context, asts: List[chapel.AstNode]
    ) -> Iterator[Tuple[chapel.AstNode, str, Optional[List[Fixit]]]]:
        """
        Runs all the rules registered with this node, yielding warnings for
        all non-silenced rules that are violated in the given ASTs.
        """

        for ast in asts:
            for rule in self.BasicRules:
                for toreport in self._check_basic_rule(context, ast, rule):
                    if self._has_internal_name(toreport[0]):
                        continue

                    yield toreport

            for rule in self.AdvancedRules:
                for toreport in self._check_advanced_rule(context, ast, rule):
                    if self._has_internal_name(toreport[0]):
                        continue

                    yield toreport
