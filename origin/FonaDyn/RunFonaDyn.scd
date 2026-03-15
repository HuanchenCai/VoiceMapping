/*RUN*/
// For starting FonaDyn directly from your Windows desktop,
// make a shortcut to this file and put that shortcut on your desktop.
// Then when you double-click the shortcut, 
//	SuperCollider will start, 
// 	the SC startup file will be opened in the IDE,
// 	FonaDyn will start, 
//	and this file will be closed. 
//  On the Mac, SuperCollider will likely crash (benignly) when FonaDyn is closed.

Document.open(thisProcess.platform.userAppSupportDir +/+ "startup.scd"); 
FonaDyn.run;
Document.openDocuments.do { | doc | if (doc.title == "RunFonaDyn.scd", { { doc.close }.defer } ) };
