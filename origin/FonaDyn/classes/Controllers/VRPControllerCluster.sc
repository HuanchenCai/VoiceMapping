// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

/*
 * Manages the buffers, synths and data fetching concerning EGG waveshape clustering.
 */

VRPControllerCluster {
	var mTarget;
	var mData;
	var mBuffer;
	var mSynthPoints, mSynthCluster;

	// States
	var mRunning; // True if it is running, false otherwise
	var mRequest; // The request for the entire buffer
	var mDone; // Condition for when it is safe to release the buffer.
	var mBufferRequester;

	// States for the Cluster Cycle data
	var mCCSynth;
	var mCCBuffer;
	var mCCBufferRequester;
	var mCCRequest;
	var mCCDone;

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
		var s = mData.settings; // General settings
		var cs = s.cluster;
		var dn = cs.nHarmonics;
		var n = dn + 1;

		busManager
		.requireAudio(\ConditionedEGG)
		.requireAudio(\GateCycle)
		.requireAudio(\AmplitudeFirst, n)
		.requireAudio(\PhaseFirst, n)
		.requireAudio(\DeltaAmplitudeFirst, dn)
		.requireAudio(\DeltaPhaseFirst, dn)
		.requireAudio(\ClusterNumber)
		.requireAudio(\GateFilteredDFT)
		.requireControl(\EGGvalid)
		.requireControl(\GateReset);
	}

	// Prepare to start - init the SynthDefs and allocate Buffers.
	// This function is always called before start.
	prepare { | libname, server, busManager, clock |
		var d = mData;
		var cd = d.cluster;
		var s = d.settings;
		var cs = s.cluster;
		var cds = s.csdft;
		var initArgs;

		VRPSDCluster.compile(libname, cs.nClusters, cs.nHarmonics, cs.learn, cds.minSamples, server.sampleRate / cds.minFrequency, cs.smoothFactor);
		if (cs.initialize,
			{	// Should used the learned data
				var centroids = cs.centroids;
				var counts = cs.pointsInCluster;
				var matrix = centroids collect: { | centroid, idx |
					centroid ++ counts[idx].asArray
				};
				initArgs = [\set, matrix];
			}, {
				// Should relearn from scratch
				initArgs = [\zero];
			}
		);

		mBuffer = KMeansRTv2.allocBuffer(server, cs.nDimensions, cs.nClusters, *initArgs);
		mBufferRequester = BufferRequester(mBuffer);

		mCCBuffer = SmoothedClusterCycle.allocBuffer(server, cs.nClusters, cs.nSamples);
		mCCBufferRequester = BufferRequester(mCCBuffer);

		mRunning = false;
		mDone = Condition();
		mCCDone = Condition();

		// Create initial requests
		value {
			var bufsize = mBuffer.numFrames * mBuffer.numChannels;
			var reqs = mBufferRequester.asRequests(0, bufsize); // The buffer is small enough that the contents should fit inside one request.
			if ( reqs.size != 1, { Error("Assertion failed!").throw } ); // Assert the assumption above
			mRequest = reqs.first;
		};

		value {
			var bufsize = mCCBuffer.numFrames * mCCBuffer.numChannels;
			var reqs = mCCBufferRequester.asRequests(0, bufsize);
			if ( reqs.size != 1, { Error("Assertion failed!").throw } ); // Assert that we only send one request!
			mCCRequest = reqs.first;
		};
	}

	// Start - Create the synths, and initiate fetching of data at the regular
	// interval given by the clock parameter.
	// This function is always called between prepare and stop.
	start { | server, busManager, clock |
		var bm = busManager; // Shorter name
		var lostDuration = mBufferRequester.lostDuration;

		var d = mData;
		var cd = d.cluster;
		var s = d.settings;
		var cs = s.cluster;

		mSynthPoints = Synth(*VRPSDCluster.generatePoints(
			bm.audio(\AmplitudeFirst),
			bm.audio(\PhaseFirst),
			bm.audio(\DeltaAmplitudeFirst),
			bm.audio(\DeltaPhaseFirst),
			mTarget,
			\addToTail)
		);

		mSynthCluster = Synth(*VRPSDCluster.nClusters(
			mBuffer,
			bm.audio(\DeltaAmplitudeFirst),
			bm.audio(\DeltaPhaseFirst),
			bm.audio(\GateFilteredDFT),
			bm.control(\EGGvalid),
			bm.control(\GateReset),
			bm.audio(\ClusterNumber),
			mTarget,
			\addToTail)
		);

		mCCSynth = Synth(*VRPSDCluster.smoothedClusterCycle(
			bm.audio(\ConditionedEGG),
			bm.audio(\GateCycle),
			bm.audio(\GateFilteredDFT),
			bm.audio(\ClusterNumber),
			mCCBuffer,
			mTarget,
			\addToTail)
		);

		mRunning = true;
		mBufferRequester.sendAll(mRequest.asArray); // Send the first request

		clock.sched(1, {
			var count = 0;

			if (cd.resetNow, {
				// Set the reset gate to open - the synthdef will automatically close it
				bm.control(\GateReset).set(1);
				cd.resetNow = false;
			});

			if ( mRunning, {
				// Request the contents of the buffer - no need to resend lost,
				// since we're only interested in the most fresh data
				mBufferRequester.sendAll(mRequest.asArray);
				mCCBufferRequester.sendAll(mCCRequest.asArray);
			}, {
				// Resend the final request if it got lost
				if ( mDone.test.not and: (mRequest.duration > lostDuration), {
					mBufferRequester.sendAll(mRequest.asArray);
				});

				if ( mCCDone.test.not and: (mCCRequest.duration > lostDuration), {
					mCCBufferRequester.sendAll(mCCRequest.asArray);
				});
			});

			if ( mRequest.data.notNil and: mDone.test.not, {
				// Dispatch request data
				var data = mRequest.data;
				var n = cs.nClusters;
				var m = cs.nDimensions;
				var d = m + 1; // # of channels in the buffer

				cd.pointsInCluster = Array.fill(n, { |v| data[d * v + m]});
				cd.centroids = Array.fill2D(n, m, { | r, c | data[d * r + c] });
				mRequest.data = nil;

				if ( mRunning.not, {
					// Signal that the final request has been processed!
					mDone.test = true; // Don't block on waits
					mDone.signal; // Signal that stop can continue and free the buffer
				});
			});

			if ( mCCRequest.data.notNil and: mCCDone.test.not, {
				// Dispatch request data
				cd.cycleData = mCCRequest.data;
				mCCRequest.data = nil;

				if (mRunning.not, {
					mCCDone.test = true;
					mCCDone.signal;
				});
			});

			// Continue if:
			if (mRunning or: mCCDone.test.not or: mDone.test.not, 3, nil)
		});
	}

	// Free the synths and buffers after finishing fetching data.
	// The synths are guaranteed to be paused at this point - so buffers should be stable.
	stop {
		// Free synths
		mSynthPoints.free;
		mSynthCluster.free;
		mCCSynth.free;

		// Stop fetching data
		// Replace mRequest with a fresh one, to avoid having it overwritten by old requests
		mRequest = mRequest.deepCopy;
		mRequest.data = nil;

		mCCRequest = mCCRequest.deepCopy;
		mCCRequest.data = nil;

		mRunning = false; // Stop fetching data
		mDone.test = false; // Will block on wait
		mCCDone.test = false;

		// Send the request and wait for it to be processed.
		mBufferRequester.sendAll(mRequest.asArray); // Potentially blocking
		mCCBufferRequester.sendAll(mCCRequest.asArray);
	}

	sync {
		// Wait for the final request to finish - or don't if mDone.test = false
		// has been executed (when the data has already been fetched), in which case it won't wait.
		mDone.wait;
		mCCDone.wait;

		mBuffer.free;
		mCCBuffer.free;
	}
}