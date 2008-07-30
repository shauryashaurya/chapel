class D {
  type elemType;
  var x: elemType;
}

class C {
  type elemType;
  const dArray: [LocaleSpace] D(elemType);

  def C(type elemType, targetLocales: [?targetLocalesDomain] locale) {
    for locid in LocaleSpace do
      on Locales(locid) do
        dArray(locid) = new D(elemType);
  }
}

var myC = new C(real(64), Locales);
writeln("myC = ", myC);
