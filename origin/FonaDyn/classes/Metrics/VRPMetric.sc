// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// VRPMetric is an abstract base class for all FonaDyn metrics
// - do not instantiate it directly.
// Each metric has a subclass defined in "MetricXxxx.sc"
// The var members and some classvar members are set by the subclasses.

VRPMetric {
	// Subclass classvars:
	// classvar <metricNumber = nil; 			// indicates desired position in array of metrics
	// classvar <symbol = \AbstractMetric;		// Symbol to identify this metric, e.g. \Qci
	// classvar <busName; 						// Symbol for the bus carrying the unscaled value
	// classvar <busRate;						// \audio or \control
	// classvar <logFileTrack;					// track number for this metric in Log files
	// 	 Must be accessed as logFileTrack.value, or logFileTrack.value(nHarmonics) for MetricHRFegg

	var <>csvName;					// String name for columns in map files
	var <>csvPrecision=1e-05;     	// Parameter for .round(aFloat) when saving to .csv files
	var <>defName;					// Pathname to an optional text file that can initialize this metric
	var <>minVal, <>maxVal;			// Limits for the color mappings
	var myColorMap;
	var <>minColor = 0.0;
	var <>maxColor = 1.0;			// Color map positions for minVal and maxVal (0...1)
	var <>rangeLow, <>rangeHigh; 	// Limits for standardization for clustering
	var <>plotMin=0.0, <>plotMax=1.0;	// y axis limits in the curve-plotting panel
	var <palette;					// Palette function
	var fnPaletteRedGreenDiff, fnPaletteRedBlueDiff, fnPaletteExternal;
	var <msgGUIlimits; 				// minVal, maxVal and scaling bundled in a message
	var <msgStandardize;			// defines the mapping function for clustering of this metric
	var <>menuText;					// String for the layer menu
	var <>trendText;				// Info text on the mapping's trend
	var <>trendTextColor;   		// Colour for the trend text
	var <>colorBarText;				// String for the color bar
	var <>colorBarWarpType; 		// Color axis \lin or \exp
	var <>unit;						// Metric unit if applicable, e.g. "dB"
	var bDifferencing;				// True if a metric difference should be displayed
//	var fnNum;

	classvar <fnPrePostPalette;
	classvar colorPre, colorPost;
	classvar cvdTableFile, cvdTableFileDiscrete;
	classvar cvdColor, cvdColorDiscrete;
	classvar diffMapStrRG = "DiffRedGreen.csv";
	classvar diffMapStrRB = "DiffRedBlue.csv";
	classvar diffMapRG, diffMapRB; // ColorMap objects

	*new { arg file=nil;
		^super.new.init(file);
	}

	*initClass {
		// Special coloring for DIFF-maps underlap regions
		colorPost = Color.gray(0.6);
		colorPre = Color.hsv(0.83, 0.4, 0.8);
		fnPrePostPalette = { arg v;
			var color = switch (v)
			{ -1 } { colorPre }
			{  1 } { colorPost }
			{ Color.gray(0.3) };
			color
		};
		cvdTableFile = "";  		// no external continuous shared colormap
		cvdTableFileDiscrete = "";  // no external discrete shared colormap
	}

	// Each argument must be a pathname to a .csv file of RGB values
	// Set it to "" to remove the respective color remapping
	*configureCVDcolors { arg mapFile=nil, mapFileDiscrete=nil, colorSetFile=nil;
		// Note where the SC extensions are stored
		FonaDyn.setPaths;
		ColorMap.setDefaultPath(FonaDyn.fdExtensions +/+ "FonaDynTools/colormaps");
		diffMapRG = ColorMap.new();
		diffMapRG.load(diffMapStrRG);
		diffMapRB = ColorMap.new();
		diffMapRB.load(diffMapStrRB);

		// A colormap file is supplied to be shared by all continuous metrics
		// (except Clarity and CSE)
		if (mapFile.notNil, {
			cvdTableFile = mapFile;
			if (cvdTableFile.isEmpty.not, {
				var nColors;
				cvdColor = ColorMap.new();
				nColors = cvdColor.load(cvdTableFile, true);
				format("Loaded % colors from %", nColors, cvdTableFile).postln;
			})
		});

		// A colormap file is supplied for the clustered layers only
		if (mapFileDiscrete.notNil, {
			cvdTableFileDiscrete = mapFileDiscrete;
			if (cvdTableFileDiscrete.isEmpty.not, {
				var nColors;
				cvdColorDiscrete = ColorMap.new();
				nColors = cvdColorDiscrete.load(cvdTableFileDiscrete, true);
				format("Loaded % colors from %", nColors, cvdTableFileDiscrete).postln;
			})
		});

		// A whole setup is requested;
		// but this must be deferred until all the metrics have been instantiated.
		// Just set a global filename variable.
		if (colorSetFile.notNil, {
			if (colorSetFile.isEmpty, {
				~colorSetFileName = ""
			}, {
				~colorSetFileName = colorSetFile;
			})
		});
	} /* configureCVDcolors */

	init { arg file=nil;
		trendTextColor = Color.black; 		// default
		trendText = "→ Green: increased";   // dummy setting
		msgStandardize = msgStandardize ? ['linlin', rangeLow, rangeHigh, 0, 1] ;
		myColorMap = nil;
	}

	fnNum { | str |
		var ret;
		ret = str.notNil
		and: { str.class == String }
		and: { str.notEmpty }
		and: { str.findRegexp("[0-9]").notEmpty };
		^ret
	}


	installColorMapping { arg mapFile, minCol, maxCol, minValue, maxValue;
		var retVal = 0, nColors;
		myColorMap = ColorMap.new();
		nColors = myColorMap.load(mapFile, true);
		if (nColors <= 0, {
			myColorMap = nil;
			retVal = -1
		}, {
			if (this.fnNum(minCol),   { minColor = minCol.asFloat });
			if (this.fnNum(maxCol),   { maxColor = maxCol.asFloat });
			if (this.fnNum(minValue), { minVal = minValue.asFloat });
			if (this.fnNum(maxValue), { maxVal = maxValue.asFloat });
			// format("file: %, left %, right %, min %, max %", mapFile, minColor, maxColor, minVal, maxVal).postln;
		});
		^retVal
	}

	initPalettes { arg index=nil;
		var colorMap, fnScaler, palMethod;

		// This is a messy trap, but val can be passed as nil, for reasons as yet unknown
		fnScaler = { arg val=0.0; if (val.isNil, 0.0, { val.linlin(minVal, maxVal, minColor, maxColor) }) };

		colorMap = myColorMap ? cvdColor ;
		palMethod = if (colorMap.colorCount > 20, { \rawPaletteFunc }, { \smoothPaletteFunc });
		^{ arg v=0.0; colorMap.perform(palMethod).(fnScaler.(v)) };
	}

	initPalettesDiff { arg index;
		fnPaletteRedGreenDiff = { arg v=0.0;
			var cSat, inVal;
			if (v.class == Array, {
				inVal = v[index];
			}, {
			 	inVal = v;
			});
			diffMapRG.smoothPaletteFunc.(inVal.linlin(minVal, maxVal, 0.0, 1.0))
		};

		fnPaletteRedBlueDiff = { arg v=0.0;
			var cSat, inVal;
			if (v.class == Array, {
				inVal = v[index];
			}, {
			 	inVal = v;
			});
			diffMapRB.smoothPaletteFunc.(inVal.linlin(minVal, maxVal, 0.0, 1.0))
		};
	}

	initPalettesExp {
		var colorMap, fnScaler;

		// This is a messy trap, but val can be passed as nil, for reasons as yet unknown
		fnScaler = { arg val=0.0; if (val.isNil, 0.0, { val.explin(minVal, maxVal, minColor, maxColor) }) };

		colorMap = myColorMap ? cvdColor;
		^{ | v=0.0 | colorMap.smoothPaletteFunc.(fnScaler.(v)) };
	}

	initPalettesExpDiff { arg index;
		fnPaletteRedGreenDiff = { arg v;  // red...green
			diffMapRG.smoothPaletteFunc.(v.explin(minVal, maxVal, 0.0, 1.0))
		};

		fnPaletteRedBlueDiff = { | v | // red...blue
			diffMapRB.smoothPaletteFunc.(v.explin(minVal, maxVal, 0.0, 1.0))
		};
	}

	initPalettesDiscrete { arg nClusters;
		var colorMap;

		// Cluster diff maps always use ratios
		this.initPalettesExp;

		// Use this only to get the base cluster colors, not the faded ones
		colorMap = myColorMap ? cvdColorDiscrete;
		^{ | val | colorMap.steppedPaletteFunc(nClusters).(val.linlin(0.0, nClusters, 0.0, 0.999)) };
	}

	setDifferencing { | bDiff |
		bDifferencing = bDiff;
		this.configFromCode(nil);
		^if (bDiff, { "Differencing"+csvName } , { csvName });
	}

	fnStandardizeMsg {
		// Updates these settings when called
		// If not initialized, or not overridden,
		// use GUI limits as default values
		rangeLow  = rangeLow  ? minVal;
		rangeHigh = rangeHigh ? maxVal;
		^msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1, nil];  // nil = don't clip!
	}

	getPaletteFunc {
		^palette;
	}

	getColorPalette { arg fnDefault, isExp=false;
		var pal = fnDefault;
		if (myColorMap.notNil or: (cvdTableFile.isEmpty.not), {
			fnPaletteExternal = if (isExp, { this.initPalettesExp }, { this.initPalettes });
			pal = fnPaletteExternal;
		});
		^pal
	}

	getColorPaletteDiscrete { arg fnDefault, nClusters;
		var pal = fnDefault;
		if (myColorMap.notNil or: (cvdTableFileDiscrete.isEmpty.not), {
			fnPaletteExternal = this.initPalettesDiscrete(nClusters);
		    pal = fnPaletteExternal;
		});
		^pal
	}

	getColorPaletteDiff { arg isExp=false, index=nil;
		var fnPalette;

		if (isExp, { this.initPalettesExpDiff }, {	this.initPalettesDiff(index) } );
		fnPalette = if (myColorMap.notNil or: (cvdTableFile.isEmpty.not), { fnPaletteRedBlueDiff }, { fnPaletteRedGreenDiff } );
		^fnPalette
	}

	setClusters { | nClusters, nCluster |
		// Dummy no-op, overridden by VRPClusterMaps
	}

	// Apply content and color to View tf
	setTrendText { | tf |
		// These can be constants or functions, so .value them
		tf.string_(trendText.value);
		tf.stringColor_(trendTextColor.value)
	}

	///////// For Matlab: ///////////////////////////////////////

	cMap { arg shades=20, bLog=false;
		var color, val;
		var rgbArray, step;
		var rgbArrayString = " ";
		if (bLog == true)
		{
			step = (maxVal/minVal)**((shades+1).reciprocal);
			rgbArray = shades collect: { | n |
				val = minVal*(step**n);
				color = this.palette.(val).asArray[0..2].round(0.001);
				// a bracketed RGB triplet, but remove the commas:
				color.asCompileString.tr($, , $ )
			}
		} {
			step = (maxVal-minVal)/shades;
			rgbArray = shades collect: { | n |
				val = (minVal + (n*step));
				color = this.palette.(val).asArray[0..2].round(0.001);
				// a bracketed RGB triplet, but remove the commas:
				color.asCompileString.tr($, , $ )
			};
		};

		rgbArray do: { | triplet |
			rgbArrayString = rgbArrayString ++ "\t" ++ triplet ++ ";\n" ;
		};

		^("[" ++ rgbArrayString ++ "]");
	}

	cLims {
		^[minVal, maxVal].asCompileString;
	}

	//////////////////////////////////////////////////////////

	// UNDOCUMENTED FEATURE - PROBABLY NOT NECESSARY
	configFromFile { arg defFile;
		var tmpArray;
		var lines;
		tmpArray = FileReader.read(defFile, skipEmptyLines: true, delimiter: $§);
		// FileReader brackets each line in [  ] - strip them off
		lines = tmpArray.collect({ arg s, i; var str = s.asString; str[2..(str.size-3)] });
		~meVRPMetric = this;
		lines do: { | str, i | interpret("~meVRPMetric."++str) };
		format("Metric % loaded: %", csvName, defFile).postln;
		defName = defFile;
	}
}

