// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// This version treats both LF and CR+LF as single line breaks.
// Sten Ternström August 2022
//
LineFileReader : FileReader {
	next {
		var c, record, string = String.new;
		while {
			c = stream.getChar;
			c.notNil
		} {
			if (c == delimiter) {
				if (skipBlanks.not or: { string.size > 0 }) {
					record = record.add(string);
					string = String.new;
				}
			} {		// This is the changed behaviour:
				if (c == $\n) {
					if (string.endsWith("\r")) { string = string.split($\r)[0] } ;
					record = record.add(string);
					string = String.new;
					if (skipEmptyLines.not or: { (record != [ "" ]) }) {
						^record
					};
					record = nil;
				}{
					string = string.add(c);
				}
			}
		};
		if (string.notEmpty) { ^record.add(string) };
		^record;
	}
}