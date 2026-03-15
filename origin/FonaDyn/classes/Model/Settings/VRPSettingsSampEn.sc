// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
// Copyright (C) 2016-2025 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// The GUI of SampEn has been moved to the class VRPViewPlots.
// This class is kept for backward compatibility only.
// It now redirects to .settings.plots.

VRPSettingsSampEn {
	// States
	var <isVisible;
	// var <>amplitudeWindowSize; // The size of the window (in cycles) where we look for matching sequences via the Sample Entropy algorithm
	// var <>amplitudeHarmonics; // The number of harmonics we use to produce the SampEn measurement
	// var <>amplitudeSequenceLength; // The length of a matching sequence
	// var <>amplitudeTolerance; // The tolerance for matching values in the sequences
	//
	// var <>phaseWindowSize; // The size of the window (in cycles) where we look for matching sequences via the Sample Entropy algorithm
	// var <>phaseHarmonics; // The number of harmonics we use to produce the SampEn measurement
	// var <>phaseSequenceLength; // The length of a matching sequence
	// var <>phaseTolerance; // The tolerance for matching values in the sequences

	// States of check boxes - the class VRPViewSampEn has been succeeded by VRPViewPlots
	// var <bDrawSpecBal;
	// var <bDrawCPP;
	// var <bDrawSampEn;
	// var <bDrawQci;
	// var <bDrawDEGGmax;
	// var <bDrawIc;		// not used
	// var <bDrawCrest;		// not used

	//////////// For backward script compatibility with v<3.5.0 ////////////

	var <>topS;
	const metricSymbols = #[\Crest, \SpecBal, \CPP, \CSE, \Qci, \Qdelta, \Ic];
	const metricSetterSymbols = #[\bDrawCrest_, \bDrawSpecBal_, \bDrawCPP_, \bDrawSampEn_, \bDrawQci_, \bDrawDEGGmax_, \bDrawIc];
	const sampenGetters = #[
		\amplitudeWindowSize,
		\amplitudeHarmonics,
		\amplitudeSequenceLength,
		\amplitudeTolerance,
		\phaseWindowSize,
		\phaseHarmonics,
		\phaseSequenceLength,
		\phaseTolerance
	];


	*new { arg topSettings;
		^super.new.init(topSettings);
	}

	init { arg topSettings;
		isVisible = true;
		topS = topSettings;

		// Redirect the former setter functions (getters are never called from scripts)
		metricSetterSymbols do: { | sym, ix |
			this.addUniqueMethod(sym, { topS.plots.metrics_([metricSymbols[ix]]) } );
		};

		// Redirect the former <>members to the corresponding methods in .plots
		sampenGetters do: { | sym, ix |
			var setSym;
			setSym = (sym.asString ++ "_").asSymbol;
			this.addUniqueMethod(setSym, { arg thisInstance, param; topS.plots.perform(setSym, param) });
			this.addUniqueMethod(sym, { topS.plots.perform(sym) });
		};
	}

	isVisible_ { arg b;
		topS.plots.isVisible_(b);
	}

}