// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
/**
 * Manages the buffers, synths and settings concerning the calculations of the VRP display.
 */

VRPControllerVRP {
	var mData;
	var mTarget;
	var mSynthAudio;
	var mSynthCPP;
//	var mSynthCorrVoiceEGG;

	*new { | target, data |
		^super.new.init(target, data);
	}

	// Init given the target and output data structure
	// This function is called once only!
	init { | target, data |
		mTarget = target;
		mData = data;
	}

	// Tell the busManager what buses it requires.
	// This function is called before prepare.
	requires { | busManager |
		busManager
		.requireAudio(\ConditionedMicrophone)
		.requireControl(\Frequency)
		.requireControl(\Amplitude)
		.requireControl(\Clarity)
		.requireControl(\Crest)
		.requireControl(\SpecBal)
		// .requireControl(\EGGspectrum)
		// .requireControl(\MaxCorr)
		// .requireControl(\IxDelay)
		.requireControl(\CPPsmoothed)
	}

	// Prepare to start - init the SynthDefs and allocate Buffers.
	// This function is always called before start.
	prepare { | libname, server, busManager, clock |
		var bSmoothCPP = (VRPSettings.metrics[VRPSettings.icppSmoothed].class.symbol == \CPPs);
		VRPSDVRP.compile(libname, bSmoothCPP);
	}

	// Start - Create the synths, and initiate fetching of data at the regular
	// interval given by the clock parameter.
	// This function is always called between prepare and stop.
	start { | server, busManager, clock |
		var bm = busManager;

		mSynthAudio = Synth(*VRPSDVRP.analyzeAudio(
			bm.audio(\ConditionedMicrophone),
			bm.control(\Frequency),
			bm.control(\Amplitude),
			bm.control(\Clarity),
			bm.control(\Crest),
			bm.control(\SpecBal),
			mTarget),
			addAction: \addToTail
		);

		mSynthCPP = Synth(*VRPSDVRP.cppSmoothed(
			bm.audio(\ConditionedMicrophone),
			bm.control(\CPPsmoothed),
			mTarget),
			addAction: \addToTail
		);

/*		mSynthCorrVoiceEGG = Synth(*VRPSDVRP.corrVoiceEGG(
			bm.audio(\ConditionedMicrophone),
			bm.control(\EGGspectrum),
			bm.control(\MaxCorr),
			bm.control(\IxDelay),
			mTarget),
			addAction: \addToTail
		);
*/
	}

	// Free the synths and buffers after finishing fetching data.
	// The synths are guaranteed to be paused at this point - so buffers should be stable.
	stop {
		// Free synths...
//		mSynthCorrVoiceEGG.free;
		mSynthCPP.free;
		mSynthAudio.free;

		// ...and buffers
	}

	sync {
		nil
	}
}