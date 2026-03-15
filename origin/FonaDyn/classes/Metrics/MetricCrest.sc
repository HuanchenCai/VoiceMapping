// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

MetricCrest : VRPMetric {
	classvar <metricNumber; // the desired index of this metric
	classvar <symbol = \Crest;
	classvar <busName = \DelayedCrest;
	classvar <busRate = \audio;
	classvar <logFileTrack = 4;

	var fnMyPalette;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iCrestFactor;
		bDifferencing = bDiff;
		super.init(file);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode }
		);

		// map crest factor 1.414 (+3 dB) ... <4 (+12 dB) to green...red
		minVal = 1.414;
		maxVal = 4.0;

		// Scale to 1/10
		plotMin = 0.0;
		plotMax = 10.0;

		fnMyPalette = { | v |
			var cHue = v.linlin(minVal, maxVal, 0.333, 0);
			Color.hsv(cHue, 1, 1)
		};
	}

	fnStandardizeMsg {
		// Updates these settings when called
		// If not initialized, or not overridden,
		// use GUI limits as default values
		rangeLow  = rangeLow  ? minVal;
		rangeHigh = rangeHigh ? maxVal;
		^msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1, \minmax];
	}

	configFromCode {
		csvName = "Crest";		// Column title in map files
		csvPrecision = 1e-05;

		menuText = "Audio Crest Factor";		// String for the layer menu
		colorBarWarpType = \lin;	 			// Color axis \lin or \exp
		unit = "";								// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			// Color mapping of value
			palette = this.getColorPalette(fnMyPalette);
			colorBarText = "Mean crest factor";		// String for the color bar
			trendText = "→ Peakier signal";  		// String for info text
			trendTextColor = palette.(maxVal);
		}, {
			// Color mapping of delta-value
			// map crest factor difference -2 ... <2 to red...green
			minVal = -2;
			maxVal = 2;
			palette = this.getColorPaletteDiff;
			colorBarText = "Crest factor diff";		// Ditto, when differencing
			trendText = "→ Increased crest f.";  	// String for info text
			trendTextColor = palette.(maxVal);
		});
	}
}

