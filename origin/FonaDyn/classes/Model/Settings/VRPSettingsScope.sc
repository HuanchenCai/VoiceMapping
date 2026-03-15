// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPSettingsScope {
	// States
	var <>isVisible;
	var <>minSamples; // Minimum # of samples required by the MovingEGG
	var <>maxSamples; // Maximum # of samples required by the MovingEGG.
	var <>normalize; // True means it should normalize the height
	var <>movingEGGCount; // # of overlapping EGG cycles
	var <>movingEGGSamples; // # of samples representing each EGG cycle
	var <>denoise;			// true if denoising
	var <noiseThreshold;	// number for the noise threshold
	var <>validate;			// false/true checkbox

	var topS;		// the top-level settings

	*new { arg topSettings;
		^super.new.init(topSettings);
	}


	init { arg t;
		topS = t;
		isVisible = true;

		minSamples = 20;
		maxSamples = 882;
		normalize = true;

		movingEGGCount = 5;
		movingEGGSamples = 80;
		denoise = true;
		noiseThreshold = -80.0;
		validate = true;
	}

	//// For backward compatibility with v<3.5.0 /////////////
	duration_ { | time |
		topS.plots.duration = time.clip(1, 10);
	}

	noiseThreshold_ { arg nt;
		var retval = nt;
		case
		{ nt > 0.0  } { denoise = true; retval = nt.explin(0.007, 7, -120, -50, clip: \min).round }
		{ nt == 0.0 } { denoise =false }
		;
		noiseThreshold = retval;
		^retval
	}
}