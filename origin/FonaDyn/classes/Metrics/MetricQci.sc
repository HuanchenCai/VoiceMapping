// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
MetricQci : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric
	classvar <symbol = \Qci;
	classvar <busName = \Qcontact;
	classvar <busRate = \audio;
	classvar <logFileTrack = 12;
	var fnMyPalette;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iQcontact;
		bDifferencing = bDiff;
		super.init(file);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode(metricNumber) }
		);

		// large Qc=0.6 to red, small Qc=0.1 to purple
		minVal = 0.1;
		maxVal = 0.6;
		// minColor = 1/3;
		// maxColor = 1.0;

		fnMyPalette = { | v |
			var cHue = v.linlin(minVal, maxVal, 0.83, 0.0);
			Color.hsv(cHue, 1, 1)
		};
	}

	configFromCode { arg metNumber;
		symbol = \Qci;			// Symbol to identify this metric, e.g. \Qci
		csvName = "Qcontact";	// Column title in map files
		menuText = "Qci - EGG contact quotient";	// String for the layer menu
		colorBarWarpType = \lin;	 				// Color axis \lin or \exp
		unit = "";									// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			// Color mapping of value
			palette = this.getColorPalette(fnMyPalette);
			colorBarText = "Mean Qci";							// String for the color bar
			trendText = "→ Longer contact";  				// String for info text
			trendTextColor = palette.(maxVal);
		}, {

			// Color mapping of delta-value
			// Diff/ratio: lower Qci=-0.2 to red, larger Qci=0.2 to green; mid=0 to grey
			minVal = -0.2;
			maxVal = 0.2;
			palette = this.getColorPaletteDiff;
			colorBarText = "Qci diff"; 			// Ditto, when differencing
			trendText = "→ Increased contact";  // String for info text
			trendTextColor = palette.(maxVal);
		});
	}
}

