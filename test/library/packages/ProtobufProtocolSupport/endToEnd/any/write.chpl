use any;
use IO;

var file = open("out", ioMode.cw);
var writingChannel = file.writer(locking=false);

var messageObj = new anyTest();
var obj = new test();

messageObj.a = 123;

obj.a = "chapel";
obj.b = true;
messageObj.anyfield.pack(obj);

messageObj.serialize(writingChannel);
