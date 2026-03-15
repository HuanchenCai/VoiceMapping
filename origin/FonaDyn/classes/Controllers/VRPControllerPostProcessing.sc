// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

/* The group "target" used to be near the end of the node chain,
   but has been moved earlier so that the ClusterPhon stuff can access
   the delayed signals. The name "...PostProcessing" has been kept
   for the time being. It will be changed to "Delays".
*/

VRPControllerPostProcessing {
	var mData;
	var mTarget;
	var mSynthDelay;

	*new { | target, data |
		^super.new.init(target, data);
	}

	// Init given the target and output data structure
	// This function is called once only!
	init { | target, data |
		mTarget = target;
		mData = data; // General data
	}

	// Tell the busManager what buses it requires.
	// This function is called before prepare.
	requires { | busManager |
		var d = mData;
		var s = d.settings;
		var ss = s.sampen;

		busManager
		.requireControl(\Frequency)
		.requireControl(\Amplitude)
		.requireControl(\Clarity)
		.requireControl(\EGGvalid)
		.requireControl(\Crest)
		.requireControl(\SpecBal)
		.requireAudio(\GateCycle)
		.requireAudio(\GateDelayedCycle)
		.requireAudio(\DelayedFrequency)
		.requireAudio(\DelayedAmplitude)
		.requireAudio(\DelayedClarity)
		.requireAudio(\DelayedEGGvalid)
		.requireAudio(\DelayedCrest)
		.requireAudio(\DelayedSpecBal);
	}

	// Prepare to start - init the SynthDefs and allocate Buffers.
	// This function is always called before start.
	prepare { | libname, server, busManager, clock |
		var d = mData;
		var s = d.settings;
		var cs = s.csdft;

		VRPSDPostProcessing.compile(libname, (server.sampleRate / cs.minFrequency).ceil );
	}

	// Start - Create the synths, and initiate fetching of data at the regular
	// interval given by the clock parameter.
	// This function is always called between prepare and stop.
	start { | server, busManager, clock |
		var bm = busManager;

		// Instantiate the Synths
		mSynthDelay = Synth(*VRPSDPostProcessing.delay(
			bm.audio(\GateCycle),
			bm.audio(\GateDelayedCycle),
			bm.control(\Clarity),
			bm.control(\EGGvalid),
			bm.control(\Frequency),
			bm.control(\Amplitude),
			bm.control(\Crest),
			bm.control(\SpecBal),
			bm.audio(\DelayedClarity),
			bm.audio(\DelayedEGGvalid),
			bm.audio(\DelayedFrequency),
			bm.audio(\DelayedAmplitude),
			bm.audio(\DelayedCrest),
			bm.audio(\DelayedSpecBal),
			mTarget,
			\addToTail )
		);

	}

	// Free the synths and buffers after finishing fetching data.
	// The synths are guaranteed to be paused at this point - so buffers should be stable.
	stop {
		// Free the Synths
		mSynthDelay.free;
	}

	sync { nil } // Nothing to do
}