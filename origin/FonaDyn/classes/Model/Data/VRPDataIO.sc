// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPDataIO {
	// Data
	var <>filePathAudio;
	var <>filePathLog;
	var <>filePathCycleDetectionLog;
	// var <>filePathOutputPoints;
	// var <>filePathFrequencyAmplitude;
	// var <>filePathSampEn;
	var <>filePathGates;
	var <>filePathExtraChannels;

	var <>eof;
	var <>clip;

	*new { | settings |
		^super.new.init(settings);
	}

	init { | settings |
		filePathAudio = "";
		filePathLog = "";
		filePathCycleDetectionLog = "";
		// filePathOutputPoints = "";
		// filePathFrequencyAmplitude = "";
		filePathGates = "";
		filePathExtraChannels = "";

		eof = false;
		clip = false;
	}
}