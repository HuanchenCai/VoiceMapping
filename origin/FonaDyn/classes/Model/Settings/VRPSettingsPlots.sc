// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsPlots {
	// States
	var <>isVisible;
	var <>duration; // Duration of the scopes (up to duration seconds back is stored)

	var <>amplitudeWindowSize; // The size of the window (in cycles) where we look for matching sequences via the Sample Entropy algorithm
	var <>amplitudeHarmonics; // The number of harmonics we use to produce the SampEn measurement
	var <>amplitudeSequenceLength; // The length of a matching sequence
	var <>amplitudeTolerance; // The tolerance for matching values in the sequences

	var <>phaseWindowSize; // The size of the window (in cycles) where we look for matching sequences via the Sample Entropy algorithm
	var <>phaseHarmonics; // The number of harmonics we use to produce the SampEn measurement
	var <>phaseSequenceLength; // The length of a matching sequence
	var <>phaseTolerance; // The tolerance for matching values in the sequences

	// States of check boxes for the general graph plotter
	var <>plotMetrics;  		// Array of booleans, set true to plot

	*new {
		^super.new.init;
	}

	init {
		isVisible = true;
		duration = 2.0;
		plotMetrics = VRPSettings.metrics[0..VRPSettings.iLastMetric].collect { | m | false }; // No plots requested yet
	}

	metrics_ { arg aSymbols;
		var aTmp = aSymbols.collect { |e| e.asSymbol };  // in case they are "strings"
		if (aTmp.isEmpty,
			{
				plotMetrics = false ! (VRPSettings.iLastMetric+1);  // clear all plots
			}, {
				VRPSettings.metrics.do { | m, ix |
					if (aTmp.includes(m.class.symbol), { plotMetrics[ix] = true });
				}
			};
		);
	}

	graphsRequested {
		var g = [];
		plotMetrics.do { | b, ix |
			if (b == true, { g = g.add(ix) });
		};
		^g
	}

}