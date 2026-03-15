// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsCSDFT {
	// States
	var <nHarmonics; 	// The number of harmonics of interest
	var <>tau; 			// sample decay factor used by PhasePortrait for cycle separation
	var <>minSamples;	// Minimum required samples for the DFT calculations
	var <>minFrequency;	// Smallest frequency for which to calculate DFTs

	var <>method;

	classvar <methodPhasePortrait = 1;
	classvar <methodPhasePortrait2 = 2;
//	classvar <methodPeakFollower = 1;

	*new {
		^super.new.init;
	}

	nHarmonics_ { |n|
		nHarmonics = n;
	}

	init {
		tau = 0.95;
		minSamples = 20;
		minFrequency = 50;
		method = methodPhasePortrait2;
	}
}