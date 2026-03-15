// Copyright (C) 2017 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

/** FUNCTIONALITY REMOVED as of v1.5.6
VRPDataSampEn {
	// Data
	var <sampenPoints; // Direction in radians or nil if no SampEn value above the SampEn limit exists

	classvar <vrpWidth = 100;
	classvar <vrpHeight = 100;

	*new { | settings |
		^super.new.init(settings);
	}

	init { | settings |
		var cs = settings.cluster;
		var w = this.class.vrpWidth;
		var h = this.class.vrpHeight;

		sampenPoints = DrawableSparseArrowMatrix(h, w);  /** this entire class should be removed **/

		// Some test values
		/*value {
			var mw = w.half;
			var mh = h.half;

			sampenPoints.put(0, 0, 0); // Right, lower left corner of the VRP graph
			sampenPoints.put(h - 1, 0, 3.14159265358979); // Left, upper left corner of the VRP Graph.

			sampenPoints.put(mh + 1, mw, 3.14159265358979 / 2); // Up
			sampenPoints.put(mh - 1, mw, 3 * 3.14159265358979 / 2); // Down
			sampenPoints.put(mh, mw - 1, 3.14159265358979); // Left
			sampenPoints.put(mh, mw + 1, 0); // Right
			sampenPoints.put(mh, mw + 2, 2 * 3.14159265358979); // Still Right

			sampenPoints.put(mh + 1, mw + 1,  1 * 3.14159265358979 / 4); // Right/Up
			sampenPoints.put(mh + 1, mw - 1,   3 * 3.14159265358979 / 4); // Left/Up
			sampenPoints.put(mh - 1, mw - 1,  5 * 3.14159265358979 / 4); // Left/Down
			sampenPoints.put(mh - 1, mw + 1, 7 * 3.14159265358979 / 4); // Right/Down
		};*/
	}
}

**/