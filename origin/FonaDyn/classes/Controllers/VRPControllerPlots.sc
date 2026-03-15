// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPControllerPlots {
	var mData;
	var mDataLayers;
	var mTarget;
	var mSynthPrepare; // Prepare step for the BusListeners - generating timestamps/audio rate gate etc

	// The list mSymbols must match the sequence in cycle_tool.assign(\VRPData, ...) from \Crest and onwards
	var mSymbols;
	var cIxEGG, cIxPhon;

	var mBufferMovingEGG;
	var mSynthMovingEGG;
	var mConditionMovingEGG;
	var mBufferRequesterMovingEGG;
	var mRequestMovingEGG;

	var mBusListenerGoodCycles; // Per cycle bus listener using only good cycles
	var mBusListenerCycleSeparation; // Per cycle bus listener using the raw cycles (unfiltered gate from the cycle separation)

	// States
	var mRunning;

	*new { | target, data |
		^super.new.init(target, data);
	}

	// Init given the target and output data structure
	// This function is called once only!
	init { | target, data |
		mTarget = target;
		mData = data;
		mBusListenerGoodCycles = BusListener();
		mBusListenerCycleSeparation = BusListener();
		mSymbols = VRPSettings.metrics.collect { | m, ix | m.class.symbol };

		// -2 because \Density and \Clarity are not in cycleData[] (below)
		cIxEGG  = mSymbols.indexOf(\ClustersEGG) - 2;
		cIxPhon = mSymbols.indexOf(\ClustersPhon) - 2;
	}

	// Tell the busManager what buses it requires.
	// This function is called before prepare.
	requires { | busManager |
		var d = mData;
		var s = d.settings;

		busManager
		.requireAudio(\Timestamp)
		.requireAudio(\SampEn)
		.requireAudio(\GateCycle)
		.requireAudio(\GateFilteredDFT)
		.requireAudio(\DEGGmax)
		.requireAudio(\Qcontact)
		.requireAudio(\Icontact)
		.requireAudio(\HRFEGG)
		.requireAudio(\ClusterNumber)
		.requireControl(\PhonClusterNumber)
		.requireControl(\Frequency)
		.requireControl(\Amplitude)
		.requireControl(\Clarity)
		.requireControl(\Crest)
		.requireControl(\SpecBal)
		.requireControl(\CPPsmoothed)
		.requireControl(\NoiseThreshold)
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
		var bm = busManager;
		var d = mData;
		var sd = d.scope;
		var s = d.settings;
		var ss = s.scope;
		var sp = s.plots;
		var vrpd = d.vrp;

		// Generate a base path for the output
		var dir = s.io.outDir;
		var timestamp = d.general.timestamp;
		var base_path = dir +/+ timestamp;

		// Create 2 bus assignment tools for both rates
		var cycle_tool = BusListener.newBusAssignmentTool;
		var cycle_separation_tool = BusListener.newBusAssignmentTool;
		var graphsToDraw;

		var clarityMap = vrpd.layers[\Clarity].mapData;
		var clarityThresh = s.vrp.clarityThreshold;

		sd.busThreshold = bm.control(\NoiseThreshold);

		// Compile the synthdefs
		VRPSDScope.compile(libname, ss.movingEGGCount, ss.minSamples, ss.maxSamples, ss.normalize);

		// Create the directory if necessary.
		if (File.type(dir) != \directory, { File.mkdir(dir); });

		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////
		// Add the handlers for the cycle rate bus listener
		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////

		cycle_tool.assign(\SampEnScope,
			([bm.audio(\Timestamp)] ++ s.plots.graphsRequested.collect { | mIndex, i |
				var metric = VRPSettings.metrics[mIndex];
				if (metric.class.busRate == \control,
					{ bm.control(metric.class.busName) },
					{ bm.audio(metric.class.busName) }
				)
			})
		);

		cycle_tool.assign(\VRPData,
			[
				bm.audio(\DelayedFrequency),    // 0
				bm.audio(\DelayedAmplitude),    // 1
				bm.audio(\DelayedClarity),		// 2
				bm.audio(\DelayedEGGvalid),		// 3
				bm.audio(\DelayedCrest),		// 4
				bm.audio(\DelayedSpecBal),		// 5
				bm.control(\CPPsmoothed),   	// 6
				bm.audio(\SampEn),				// 7
				bm.audio(\DEGGmax),				// 8
				bm.audio(\Qcontact),			// 9
				bm.audio(\Icontact),			// 10
				bm.audio(\HRFEGG),				// 11
				bm.audio(\ClusterNumber),		// 12
				bm.control(\PhonClusterNumber)	// 13
			]
		);

		// Prepare an ordered array of VRPDataLayer.mapData objects
		// - they are DrawableSparseMatrix'es. It must match the end of the sequence
		// returned by the \VRPData  handler into the 'frame' argument.
		mDataLayers = mSymbols.collect { | sym, ix | vrpd.layers[sym] };

		// Add the handler to grab scope data for the Plots scope
		mBusListenerGoodCycles
		.addHandler(\scopeSampEn, \scope,
			cycle_tool.indices(\SampEnScope),
			sp.duration,
			{
				| data |
				sd.sampen = data;
			}
		)

		// Add the handler to grab the VRPData
		.addHandler(\vrp, \custom, {
			| data |
			data.dataAsFrames do: { | frame |
				var cycleData;
				var freq, amp, clarity, eggValid;
				var idx_midi, idx_spl;
				var invDensity, putMeanArgs, densityNew = 0;

				// Set up variables to receive the data
				#freq, amp, clarity, eggValid ... cycleData = frame[ cycle_tool.indices(\VRPData) ];

				// There is a grid that is VRPDataVRP.vrpWidth x VRPDataVRP.vrpHeight in size,
				// that we need to map these values to
				idx_midi = VRPDataVRP.frequencyToIndex( freq );
				idx_spl = VRPDataVRP.amplitudeToIndex( amp );

				// A clarity TEST SHOULD NOT BE NEEDED
				// SINCE THIS HANDLER IS TRIGGERED BY \GateFilteredDFT
				if ((clarity >= clarityThresh) and: { eggValid.asBoolean }, {
					densityNew = mDataLayers[0].mapData.increment(idx_spl, idx_midi, 1);
					invDensity = densityNew.reciprocal;
					putMeanArgs = [idx_spl, idx_midi, densityNew-1, invDensity];
					mDataLayers[2..].do { | layer, ix |
						if (layer.class == VRPDataClusterMap, {
							var cNum = cycleData[ix];
							layer.mapData(cNum+1).addPercent(idx_spl, idx_midi, 1, invDensity);
							layer.setMaxCluster(idx_spl, idx_midi, densityNew);
						}, {
							layer.mapData.putMean(putMeanArgs, cycleData[ix]);
						});
					};
				}
				);

				// Update maxDensity
				if ( (vrpd.maxDensity ? 0) < densityNew, {
					vrpd.maxDensity = densityNew;
				});

				vrpd.currentCluster = cycleData[cIxEGG];
				vrpd.currentClusterPhon = cycleData[cIxPhon];
			}; // End do

		});

		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////

		cycle_separation_tool
		.assign(\vrp,
			[
				bm.control(\Frequency),
				bm.control(\Amplitude),
				bm.control(\Clarity),
				bm.control(\EGGvalid)
			]
		);

		mBusListenerCycleSeparation
		.addHandler(\vrp, \custom, {
			| data |
			var freq, amp, clarity, eggValid;
			var indices = cycle_separation_tool.indices(\vrp);

			data.dataAsFrames do: { | frame |
				var idx_midi;
				var idx_spl;

				// There is a grid that is VRPDataVRP.vrpWidth x VRPDataVRP.vrpHeight in size,
				// to which we need to map these values

				#freq, amp, clarity, eggValid = frame[ indices ];
				idx_midi = VRPDataVRP.frequencyToIndex( freq );
				idx_spl = VRPDataVRP.amplitudeToIndex( amp );

				// Set the clarity measurement
				// vrpd.clarity.put(idx_spl, idx_midi,
				clarityMap.put(idx_spl, idx_midi,
					max( clarity, clarityMap.at(idx_spl, idx_midi) ? 0 )
				);
			};

			// Update the current Frequency and Amplitude
			vrpd.currentFrequency = freq;
			vrpd.currentAmplitude = amp;
			vrpd.currentClarity = clarity;
			vrpd.currentEGGvalid = eggValid;
		});

		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////
		// Prepare the bus listeners
		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////

		mBusListenerGoodCycles.prepare(libname, server,
			cycle_tool.buses,
			bm.audio(\GateFilteredDFT),
			clock
		);

		mBusListenerCycleSeparation.prepare(libname, server,
			cycle_separation_tool.buses,
			bm.audio(\GateCycle),
			clock
		);

		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////
		// Prepare for the Moving EGG
		//////////////////////////////////////////////////////////////////////////////////////////////////////////////////

		mBufferMovingEGG = MovingEGG.allocBuffer(server, ss.movingEGGCount, ss.movingEGGSamples);
		mBufferRequesterMovingEGG = BufferRequester(mBufferMovingEGG);
		mConditionMovingEGG = Condition();

		value {
			var bufsize = mBufferMovingEGG.numFrames * mBufferMovingEGG.numChannels;
			var reqs = mBufferRequesterMovingEGG.asRequests(0, bufsize);
			// Assert that we read the entire buffer
			if ( reqs.size != 1, { Error("Assertion failed!").postln; });
			mRequestMovingEGG = reqs[0];
		};
	}

	// Start - Create the synths, and initiate fetching of data at the regular
	// interval given by the clock parameter.
	// This function is always called between prepare and stop.
	start { | server, busManager, clock |
		var bm = busManager;

		// Start the preparation synth
		mSynthPrepare = Synth(*VRPSDScope.prepare(
			bm.audio(\Timestamp),
			mTarget,
			\addToTail)
		);

		// Start the bus listener
		mBusListenerGoodCycles.start(server, mTarget, clock);
		mBusListenerCycleSeparation.start(server, mTarget, clock);

		// Init movingEGG
		mSynthMovingEGG = Synth(*VRPSDScope.movingEGG(
			bm.audio(\GateCycle),
			bm.audio(\ConditionedEGG),
			mBufferMovingEGG,
			mTarget,
			\addToTail)
		);

		// Start fetching the buffer for the movingEGG.
		mRunning = true;
		clock.sched(1, {
			if ( mRunning, {
				// Request the contents of the buffer - no need to resend lost,
				// since we're only interested in the most fresh data
				mBufferRequesterMovingEGG.sendAll(mRequestMovingEGG.asArray);
			}, {
				// Resend the final request if it got lost
				if ( mConditionMovingEGG.test.not
					and: (mRequestMovingEGG.duration > mBufferRequesterMovingEGG.lostDuration),
					{
						mBufferRequesterMovingEGG.sendAll(mRequestMovingEGG.asArray);
					}
				);
			});

			if ( mRequestMovingEGG.data.notNil and: mConditionMovingEGG.test.not, {
				// Dispatch request data
				mData.scope.movingEGGData = mRequestMovingEGG.data;
				mRequestMovingEGG.data = nil;

				if ( mRunning.not, {
					// Signal that the final request has been processed!
					mConditionMovingEGG.test = true; // Don't block on waits
					mConditionMovingEGG.signal; // Signal that stop can continue and free the buffer
				});
			});

			// Continue if:
			if (mRunning or: mConditionMovingEGG.test.not, 3, nil)
		});
	}

	// Free the synths and buffers after finishing fetching data.
	// The synths are guaranteed to be paused at this point - so buffers should be stable.
	stop {
		// Free the synths
		mSynthPrepare.free;
		mSynthMovingEGG.free;

		// Stop the bus listeners
		mBusListenerGoodCycles.stop;
		mBusListenerCycleSeparation.stop;

		// Signal that we want to wait on the condition
		mConditionMovingEGG.test = false;

		// Copy the request to ensure that we will make one final read after stop
		mRequestMovingEGG = mRequestMovingEGG.deepCopy;
		mRequestMovingEGG.data = nil;

		mBufferRequesterMovingEGG.sendAll(mRequestMovingEGG.asArray);

		// Tell the scheduled reads to stop
		mRunning = false;
	}

	sync {
		mBusListenerGoodCycles.sync;
		mBusListenerCycleSeparation.sync;

		mConditionMovingEGG.wait;
		// Ok to free the buffers now
		mBufferMovingEGG.free;
	}
}