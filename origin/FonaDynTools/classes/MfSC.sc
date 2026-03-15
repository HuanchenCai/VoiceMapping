// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //


// This is a patcher of template m-files for Matlab
// It reads files called "*.template.m",
// finds text enclosed by <: and :>,
// submits this text to the SuperCollider interpreter,
// inserts the results where the brackets were,
// and puts the patched text into the "*.m* file.
// Lines beginning with %!! are skipped entirely.
// This helps keeping the FonaDyn*.m files up to date.
// The mechanism can be used from any SC project to make customized m-files.

MfSC {
	var <templatesPath;
	var <targetPath;
	var mTemBufArray;
	var mOutBufArray;
	var outBufStr;
	var bEcho;

	const lParen = "<:";   // must consist only of single-byte characters
	const rParen = ":>";   // because regexp can't deal with the others
	const templateComment = "%!!";  // Lines beginning in %!! are skipped entirely.
	const regPattern = "(?:<:)[[:print:]]+?(?:>)";  // Yeah, figure that out...

	*new { | templatesPath, targetPath, echo |
		^super.new.init(templatesPath, targetPath, echo);
	}

	init { | temPath, tgPath, echo=false |
		targetPath = tgPath;
		if (temPath.isNil, { templatesPath = Platform.userAppSupportDir +/+ "matlab" +/+ "templates" });
		if (targetPath.isNil, { targetPath = Platform.userAppSupportDir +/+ "matlab"});
		outBufStr = "";
		mTemBufArray = [];
		bEcho = echo;
	}

	*stringArray { | array |
		^array
	}

	*stringArrayArgs { | ... strings |
		^strings.asCompileString
	}

	updateAllMfiles {
		var list = List();
		var pn = PathName.new(templatesPath);

		// Make a list of all *.template.m files in templatesPath
		pn.filesDo { | n |
			if (n.fileName.toLower.endsWith(".template.m"))
			   { list = list.add(n.fileName.split($.)[0]) };
		};

		// Invoke writeMfile on all of them, to targetPath
		list do: { | n |
			n.postln;
			this.writeMfile(n);
		};
	}

	writeMfile { arg funcSymbol;
		var filePath;
		this.fillTemplate(funcSymbol);
		if (mTemBufArray.isEmpty, { ^false });
		filePath = targetPath +/+ funcSymbol.asString ++ ".m";
		File.use(filePath, "w", { | file |
			mOutBufArray do: { | line |
				file << line; file.put($\r); file.nl;
			}
		});
	}

	fillTemplate { arg funcSymbol;
		if (this.prLoad(funcSymbol), {
			mOutBufArray = mTemBufArray.collect { | line, ix | this.prSubst(line) };
		});
	}

	prStripBrackets { arg bracketedStr;
		^bracketedStr[2..(bracketedStr.size-3)].asString
	}

	prLoad { arg funcMfileSym;
		var tmpArray, tmp2;
		var temFilePath = templatesPath +/+ funcMfileSym.asString ++ ".template.m";
		mTemBufArray = [];
		if (File.exists(temFilePath).not, {
			^false;
		});
		// Open the template file, and read all lines into an array of strings
		// This is done by interpreting SC code.
		// Specifying § as the column delimiter means that it will interpret almost anything.
		// This is useful, but can be a security problem.
		tmpArray = LineFileReader.read(temFilePath, skipEmptyLines: false, delimiter: $§);
		// (Line)FileReader returns an array of strings for each line
		// take only the first one
		tmp2 = tmpArray.collect( { |v, i|
			v[0]
		});
		tmp2 do: { | str, line |
			var nakedStr = str;
			if (nakedStr.stripWhiteSpace.beginsWith(templateComment).not,
				{
					mTemBufArray = mTemBufArray.add(nakedStr);
				}
			);
		};
		^true
	}

	prSubst { arg lineStr;
		var searchedFor, linePatched, toReplace, newCode;
		var foundArray;
		newCode = "????";
		linePatched = lineStr;
		if (lineStr.stripWhiteSpace.size > 0, {
			foundArray = lineStr.findRegexp(regPattern);
			foundArray do: { | pos_str, i |
				searchedFor = this.prStripBrackets(pos_str[1]);
				toReplace = pos_str[1];
				newCode = searchedFor.interpret;
				linePatched = linePatched.replace(toReplace, newCode);
			};
		});
		if (bEcho, { linePatched.postln });
		^linePatched
	}
}
