// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
MetricClarity : VRPMetric {
	classvar <metricNumber;  	// the desired index of this metric
	classvar <symbol = \Clarity;
	classvar <busName = \Clarity;
	classvar <busRate = \control;
	classvar <logFileTrack = 3;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iClarity;
		bDifferencing = bDiff;
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode(metricNumber) }
		);
	}

	fnStandardizeMsg {
		// Updates these settings when called
		// If not initialized, or not overridden,
		// use GUI limits as default values
		rangeLow  = rangeLow  ? minVal;
		rangeHigh = rangeHigh ? maxVal;
		^msgStandardize = ['linlin', rangeLow, rangeHigh, 0, 1];
	}

	minVal_ { | vMin |
		minVal = vMin;
	}

	configFromCode { arg metNumber;
		csvName = "Clarity";	// Column title in map files
        csvPrecision = 1e-05;

		// Color mapping of value
		minVal = 0.96;		// Default value; may be changed
		maxVal = 1.0;
		palette = { | v |
			// Map values above the threshold to a green shade (brighter green the better the clarity)
			// Map values below the threshold to gray
			if (v > minVal,
				Color.green(v.linlin(minVal, maxVal, 0.5, 1.0)),
				Color.gray)
		};

		menuText = "Audio 'Clarity'";					// String for the layer menu
		trendText = { "Threshold: " + minVal.asString } ;
		trendTextColor = Color.green(0.5);
		colorBarWarpType = \lin;	 					// Color axis \lin or \exp
		unit = "";										// Unit, if applicable, e.g. "dB"

		// There is no special Diff display for Clarity
		if (bDifferencing, {
			colorBarText = "Least Clarity";				// String for the color bar
		}, {
			colorBarText = "Clarity";						// String for the color bar
		});
	}
} /* MetricClarity */

