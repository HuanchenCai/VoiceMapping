// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
// Copyright (C) 2024 by Sten Ternström

// This class creates an object that uses a loaded color map
// to create three kinds of palette functions from that map.

ColorMap {
	classvar <defaultPath = "";
	var cDelim = $; ;
	var cArray, cRows;

	*new { arg type;
		^super.new.init();
	}

	*setDefaultPath { | path |
		defaultPath = path;
	}

	init { arg file;
		cRows = 0;
	}

	colorCount {
		^cRows
	}

	colorArray {
		^cArray
	}

	load { arg csvPath, bPostHead=false;
		var c, tmpArray;
		var fPath = csvPath;
		var fName = PathName(csvPath).fileName;

		if (fName == csvPath, {
			// No folder given: add the default file location
			// fPath = Platform.userExtensionDir +/+ "FonaDynTools/colormaps" +/+ csvPath;
			fPath = defaultPath +/+ csvPath;
		});

		if (File.exists(fPath).not, {
			format("Could not find diff-map color table" + fPath.quote).error;
			^0
		});

		// Open the csv file and read the RGB values into an array
		tmpArray = LineFileReader.read(fPath, skipEmptyLines: true, skipBlanks: true, delimiter: cDelim);

		// If the first row contains only one element, it might be comma-delimited (not semicolon).
		// Try to parse it as such. This saves hassle when reading CSV files from elsewhere.
		if (tmpArray[0].size == 1, {
			tmpArray.clear;
			tmpArray = LineFileReader.read(fPath, skipEmptyLines: true, skipBlanks: true, delimiter: $,);
		});

		// Check the first character on each line
		// If it is not a digit, print the line (for a copyright notice or other info)
		// but don't include the line in the colormap
		cArray = [];
		tmpArray.do( { arg row;
			c = row[0][0];
			if (c.isDecDigit,
				{ cArray = cArray.add(row.asFloat) },
				{ if (bPostHead, {row.postln}) }
			);
		});
		^cRows = cArray.size;
	}

	// Find the nearest color, without interpolation
	rawPaletteFunc {
		^{ | val=0.0 |			// 0 <= val < 1
			var ix = (cRows * val).round.min(cRows-1);
			Color.fromArray(cArray[ix])
		}
	}

	// This method interpolates linearly in the RGB table
	// It is slower than rawPaletteFunc, but useful if the RGB table is sparse
	smoothPaletteFunc {
		^{ | val=0.0 |			// val must be between 0 and 1
			var ix = val.linlin(0.0, 1.0, 0, cRows-1.0001);
			var fraction = ix.frac;
			ix = ix.asInteger;
			Color.fromArray(blend(cArray[ix], cArray[ix+1], fraction))
		}
	}

	// This method does not blend unless more steps are requested
	// than are available in the table.
	// Call it with .steppedPalettefunc(nSteps).(value)
	steppedPaletteFunc { arg nSteps;
		var func;
		if (nSteps <= cArray.size,
			{ // fewer steps than colors: don't blend
				func = { | val=0.0 |			// 0 <= val < 1
					var ix, steps = nSteps;
					ix = (val * nSteps).round.asInteger.min(cRows-1);
					Color.fromArray(cArray[ix])
				}
			}, {
				// more steps than colors: blend
				func = { | val=0.0 |
					var rVal, ix, steps = nSteps;
					rVal = val.linlin(0.0, 1.0-(steps.reciprocal), 0.0, cRows.asFloat-1.001);
					ix = rVal.asInteger;
					Color.fromArray(blend(cArray[ix], cArray[ix+1], rVal.frac))
				}
		})
		^func
	}

}

/*

// "FonaDynDefault256.csv"
p = 256.collect { | i |
	var r = (255-i)/256;
	var h = r; // + (0.024*sin(r*6pi));
	Color.hsv(h, 1, 1).asArray[0..2].postln
};

// "RainbowFlat256.csv"
p = 256.collect { | i |
	var r = (255-i)/256;
	var h = r + (0.03*sin(r*6pi));
	Color.hsv(h, 1, 1).asArray[0..2].postln
};
// "RainbowFlatMuted256.csv"
p = 256.collect { | i |
	var r = (255-i)/256;
	var h = r + (0.024*sin(r*6pi));
	Color.hsv(h, 0.8, 1).asArray[0..2].postln
};

*/



