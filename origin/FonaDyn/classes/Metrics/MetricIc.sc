// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

MetricIc : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric
	classvar <symbol = \Ic;
	classvar <busName = \Icontact;
	classvar <busRate = \audio;
	classvar <logFileTrack = 10;

	var fnMyPalette;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iIcontact;
		bDifferencing = bDiff;
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode() }
		);

		// map large Ic=1.0 to red, small Ic=0 to blue
		minVal = 0.0;
		maxVal = 0.7;
		// minColor = 1/3;
		// maxColor = 1.0;

		fnMyPalette = { | v |
			var cHue = v.linlin(minVal, maxVal, 0.67, 0.0);
			Color.hsv(cHue, 1, 1)
		};
	}

	configFromCode {
		csvName = "Icontact";	// Column title in map files
		menuText = "Ic - EGG index of contacting";	// String for the layers menu
		colorBarWarpType = \lin;				// Color axis \lin or \exp
		unit = "";								// Unit, if applicable, e.g. "dB"

		if (bDifferencing.not, {
			// Color mapping of value
			palette = this.getColorPalette(fnMyPalette);
			colorBarText = "Mean Ic";			// String for the color bar
			trendText = "← No contact";  		// String for info text
			trendTextColor = palette.(minVal);
		}, {
			// Color mapping of delta-value
			// map lower Ic=-0.4 to red, larger Ic=0.4 to green
			// map mid=0 to grey
			minVal = -0.4;
			maxVal = 0.4;
			palette = this.getColorPaletteDiff;
			colorBarText = "Ic diff"; 			// Ditto, when differencing
			trendText = "→ Increased contacting";  // String for info text
			trendTextColor = palette.(maxVal);
		});
	}
}

