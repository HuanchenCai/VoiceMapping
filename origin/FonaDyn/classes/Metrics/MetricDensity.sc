// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

MetricDensity : VRPMetric {
	classvar <metricNumber; 		// the desired index of this metric
	classvar <symbol = \Density;
	classvar <busName = \not_used;	// This metric is not relevant for clustering
	classvar <busRate = \not_used;
	var <fnMyPalette;				// Give it a getter func for drawing gray backdrops

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iDensity;
		bDifferencing = bDiff;
		super.init(file);
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode(metricNumber) }
		);

		// Color mapping of value
		// map 1..<10000 to light...darker grey
		minVal = 1;
		maxVal = 10000;

		fnMyPalette = { | v |
			var cSat = v.explin(minVal, maxVal, 0.95, 0.25);
			Color.grey(cSat, 1);
		};
	}

	fnStandardizeMsg {
		// updates these settings when called
		^msgStandardize = ['explin', minVal, maxVal, 0, 1, \min];
	}

	configFromCode { arg metNumber;
		csvName = "Total";								// Column title in map files
		csvPrecision = 0.01;							// Allow fractions, for smoothed maps
		menuText = "Density - number of cycles";		// String for the layer menu
		colorBarText = "Density";						// String for the color bar
		colorBarWarpType = \exp;	 					// Color axis \lin or \exp
		unit = "c";										// Unit is cycles

		if (bDifferencing.not, {
			// Color mapping of value
			rangeLow = minVal;
			rangeHigh = maxVal;
			palette = this.getColorPalette(fnMyPalette, true);
			colorBarText = "Density";				// String for the color bar
			trendText = "→ more cycles";  			// String for info text
			trendTextColor = palette.(maxVal);
		}, {
			// Color mapping of density; actually a ratio, not diff
			// map lower density ×0.001 to red, larger QΔ ×1000 to green
			// map mid=0 to grey
			minVal = 0.001;
			maxVal = 1000.0;
			palette = this.getColorPaletteDiff(true);
			colorBarText = "Density ratio"; 		// Ditto, when dividing
			trendText = "→ more cycles";			// String for info text
			trendTextColor = palette.(maxVal);
			unit = "";
		});
	}

} /* MetricDensity */

