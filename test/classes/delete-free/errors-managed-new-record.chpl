record R {
}

var w = new owned R();
var x = new shared R();

var y = new unmanaged R();
var z = (new owned R()).borrow();

