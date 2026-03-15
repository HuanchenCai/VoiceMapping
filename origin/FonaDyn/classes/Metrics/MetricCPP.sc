// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
// This class can be replaced by the class "MetricCPPs"
// if smoothing of the cepstrum is desired.
// Just rename this source code file to "MetricCPP.sc.hidden",
// and rename the file "MetricCPPs.sc.hidden" to "MetricCPPs.sc".
// If there arises a class mismatch between existing data files and the class library,
// existing _VRP.csv files will be displayed with a blank CPP layer,
// and existing _cPhon.csv files will ignore the CPP metric.

MetricCPP : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric
	classvar <symbol = \CPP;
	classvar <busName = \CPPsmoothed;  // even though it is not smoothed now
	classvar <busRate = \control;
	classvar <logFileTrack = 6;
	var fnMyPalette;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.icppSmoothed;
		bDifferencing = bDiff;
		super.init(file);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode() }
		);

		// map CPP 0...+30 (dB) to blue...red
		minVal = 0.0;
		maxVal = 30.0;

		// map -50 dB to bottom and +50 dB to top
		plotMin = -50.0;
		plotMax =  50.0;

		fnMyPalette = { | v |
			var cHue = v.linlin(minVal, maxVal, 0.666, 0.0);
			Color.hsv(cHue, 1, 1);
		};
	}

	fnStandardizeMsg {
		// updates these settings when called
		^msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1]
	}

	configFromCode {
		csvName = "CPP";	// Column title in map files

		menuText = "Audio CPP";		// String for the layer menu
		colorBarWarpType = \lin;				// Color axis \lin or \exp
		unit = "dB";							// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			// Color mapping of value
			rangeLow = minVal;
			rangeHigh = maxVal;
			msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1 ];
			palette = this.getColorPalette(fnMyPalette);
			colorBarText = "Mean CPP";		// String for the color bar
			trendText = "→ Peakier cepstrum";  // String for info text
			trendTextColor = palette.(maxVal);
		} , {
			// Color mapping of delta-value
			// map CPPs difference -10...+10 (dB) to red...green
			minVal = -10;
			maxVal = 10.01;
			palette = this.getColorPaletteDiff;
			trendText = "→ increased CPP";  // String for info text
			colorBarText = "CPP diff"; 			// Ditto, when differencing
			trendTextColor = palette.(maxVal);
		});
	}
}

