// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
MetricSpecBal : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric
	classvar <symbol = \SpecBal;
	classvar <busName = \DelayedSpecBal;
	classvar <busRate = \audio;
	classvar <logFileTrack = 5;

	var fnMyPalette;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iSpecBal;
		bDifferencing = bDiff;
		super.init(file);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode(metricNumber) }
		);

		fnMyPalette = { | v |
			var cHue;
			cHue = v.linlin(minVal, maxVal, 0.333, 0);
			Color.hsv(cHue, 1, 1)
		};

		// map spectrum balance -42... 0 (dB) to green...red by default
		minVal = -42.0;
		maxVal = 0.0;

		// map -50 dB to bottom and +50 dB to top
		plotMin = -50.0;
		plotMax =  50.0;

		// minColor = 2/3;
		// maxColor = 1.0;
	}

	configFromCode { arg metNumber;
		csvName = "SpecBal";	// Column title in map files
		csvPrecision = 1e-05;
		menuText = "Audio Spectrum Balance";		// String for the layer menu
		colorBarWarpType = \lin;					// Color axis \lin or \exp
		unit = "dB";								// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			rangeLow = minVal;
			rangeHigh = maxVal;
			// Color mapping of value
			palette = this.getColorPalette(fnMyPalette);
			colorBarText = "Mean Spectrum Balance";		// String for the color bar
			trendText = "→ Stronger high freqs";	  		// String for info text
			trendTextColor = palette.(maxVal);
		}, {
			// Color mapping of delta-value
			// map specBal difference -20...+20 (dB) to red...green
			minVal = -20;
			maxVal = 20.01;
			palette = this.getColorPaletteDiff;
			colorBarText = "Spectrum Balance diff"; 	// Ditto, when differencing
			trendText = "→ Increased high freqs";	  	// String for info text
			trendTextColor = palette.(maxVal);
		});
	}
}

