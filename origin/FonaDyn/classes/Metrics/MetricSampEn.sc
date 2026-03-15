// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

MetricSampEn : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric
	classvar <symbol = \CSE; // \SampEn;
	classvar <busName = \SampEn;
	classvar <busRate = \audio;
	classvar <logFileTrack = 9;

	var colorZeroEntropy;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file=nil;
		metricNumber = number ? VRPSettings.iEntropy;
		bDifferencing = bDiff;
		colorZeroEntropy = Color.hsv(0.33, 0.1, 1);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode() }
		);
	}

	// Override the superclass method fnStandardizeMsg
	// so as to reverse the min-max range for clustering
	fnStandardizeMsg {
		// Updates these settings when called
		// If not initialized, or not overridden,
		// use GUI limits as default values
		rangeLow  = rangeLow  ? maxVal;
		rangeHigh = rangeHigh ? minVal;
		^msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1, nil];
	}

	configFromCode {
		csvName = "Entropy";	// Column title in map files
		menuText = "EGG Cycle-rate Sample Entropy";		// String for the layer menu
		colorBarWarpType = \lin;				// Color axis \lin or \exp
		unit = "";							// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			// Color mapping of value
			// Brown, saturated at 10. Should be scaled for nHarmonics in SampEn
			minVal = 0.0;
			maxVal = 10.0;

			// map 0 to bottom and 10 to top
			plotMin = 0.0;
			plotMax = 10.0;

			palette = { | v |
				var sat;
				if (v <= 0.1, { colorZeroEntropy },{
					sat = v.linlin(minVal, maxVal, 0.1, 0.95);
					Color.white.blend(Color.new255(165, 42, 42), sat);
				})
			};
			colorBarText = "Mean CSE";				// String for the color bar
			trendText = "→ Brown: changing shape";  // String for info text
			trendTextColor = Color.new255(165, 42, 42);
		}, {
			// Color mapping of delta-value
			// map lower CSE=-10 to red, larger CSE=+10 to green
			// map mid=0 to grey
			minVal = -10;
			maxVal = 10.01;
			palette = this.getColorPaletteDiff;
				// palette = { | v |
				// 	var cSat = v.abs.linlin(0, maxVal, 0, 1.0);
				// 	Color.hsv((v.sign+1)/6, cSat, 0.93+(0.07*cSat))
				// };
			colorBarText = "CSE diff"; 			// Ditto, when differencing
			trendText = "→ Less stable";  // String for info text
			trendTextColor = palette.(maxVal);
		});
		msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1, \minmax];
	}
}

