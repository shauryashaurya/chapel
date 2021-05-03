/*
 * Copyright 2021 Hewlett Packard Enterprise Development LP
 * Other additional copyright holders may be indicated within.
 *
 * The entirety of this work is licensed under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 *
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef CHPL_UAST_IDENTIFIER_H
#define CHPL_UAST_IDENTIFIER_H

#include "chpl/uast/Exp.h"
#include "chpl/queries/Location.h"
#include "chpl/queries/UniqueString.h"

namespace chpl {
namespace uast {


class Builder;

/**
  This class represents a reference to a symbol by name.
  E.g. in

  \rst
  .. code-block:: chapel

      var x = 1; // here, 'x' is not an Identifier (it is the declared symbol)
      f(x);      // here, 'f' and 'x' are Identifiers
  \endrst
 */
class Identifier final : public Exp {
 friend class Builder;

 private:
  UniqueString name_;

  Identifier(UniqueString name);
  bool contentsMatchInner(const ASTBase* other) const override;
  void markUniqueStringsInner(Context* context) const override;

 public:
  ~Identifier() override = default;
  static owned<Identifier> build(Builder* builder, Location loc, UniqueString name);
  UniqueString name() const { return name_; }
};


} // end namespace uast
} // end namespace chpl

#endif
