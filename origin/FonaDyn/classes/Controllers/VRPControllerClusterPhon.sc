// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
/*
 * Manages the buffers, synths and data fetching concerning phonation type clustering.
 */

VRPControllerClusterPhon {
	var mTarget;
	var mData;
	var mBuffer;
	var mSynth1, mSynth2;

	// States
	var mRunning; // True if it is running, false otherwise
	var mRequest; // The request for the entire buffer
	var mDone; // Condition for when it is safe to release the buffer.
	var mBufferRequester;

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
		var cs = s.clusterPhon;
		var n = cs.nMetrics;

		cs.makeBusTable();
		cs.busTable do: { | b, i |
			if (b[1] == \audio, {
				busManager.requireAudio(b[0]);
			});
			if (b[1] == \control, {
				busManager.requireControl(b[0]);
			});
		};

		busManager
		.requireAudio(\GateFilteredDFT)
		.requireControl(\PhonGateReset)
		.requireControl(\EGGvalid)
		.requireControl(\PhonClusterNumber)
		.requireControl(\ScaledMetricFirst, n);
	}

	// Prepare to start - init the SynthDefs and allocate Buffers.
	// This function is always called before start.
	prepare { | libname, server, busManager, clock |
		var d = mData;
		var cd = d.clusterPhon;
		var s = d.settings;
		var cs = s.clusterPhon;
		var cds = s.csdft;
		var initArgs;
		var setupTable = cs.busTable;
		var clarityThreshold;

		// Get the actual bus numbers and ranges into setupTable
		setupTable do: { | b, i |
			var msg = b[3];
			// Patch [1] entries with the actual bus numbers
			if (b[1] == \audio, {
				setupTable[i][2] = busManager.audio(b[0]);
			});
			if (b[1] == \control, {
				setupTable[i][2] = busManager.control(b[0]);
			});

			// Patch with non-default ranges, if available
			if (cs.rangeLows[i].notNil,  { msg[1] = cs.rangeLows[i] } );
			if (cs.rangeHighs[i].notNil, { msg[2] = cs.rangeHighs[i] } );
			setupTable[i][3] = msg;
		};

		VRPSDClusterPhon.compile(libname, cs.nClusters, cs.nMetrics, cs.learn, setupTable);

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

		mBuffer = KMeansRTv2.allocBuffer(server, cs.nMetrics, cs.nClusters, *initArgs);
		mBufferRequester = BufferRequester(mBuffer);
		mRunning = false;
		mDone = Condition();

		// Create initial requests
		value {
			var bufsize = mBuffer.numFrames * mBuffer.numChannels;
			var reqs = mBufferRequester.asRequests(0, bufsize); // The buffer is small enough that the contents should fit inside one request.
			if ( reqs.size != 1, { Error("Assertion failed!").throw } ); // Assert the assumption above
			mRequest = reqs.first;
		};
	}

	// Start - Create the synths, and initiate fetching of data at the regular
	// interval given by the clock parameter.
	// This function is always called between prepare and stop.
	start { | server, busManager, clock |
		var bm = busManager; // Shorter name
		var lostDuration = mBufferRequester.lostDuration;

		var d = mData;
		var cd = d.clusterPhon;
		var s = d.settings;
		var cs = s.clusterPhon;

		mSynth1 = Synth(*VRPSDClusterPhon.generatePoints(
			bm.control(\ScaledMetricFirst),
			mTarget,
			\addToTail)
		);

		mSynth2 = Synth(*VRPSDClusterPhon.nPhonClusters(
			mBuffer,
			bm.audio(\GateFilteredDFT),
			bm.control(\EGGvalid),
			bm.control(\ScaledMetricFirst),
			bm.control(\PhonGateReset),
			bm.control(\PhonClusterNumber),
			mTarget,
			\addToTail)
		);

		mRunning = true;
		mBufferRequester.sendAll(mRequest.asArray); // Send the first request

		clock.sched(1, {
			var count = 0;

			if (cd.resetNow, {
				// Set the reset gate to open - the synthdef will automatically close it
				bm.control(\PhonGateReset).set(1);
				cd.resetNow = false;
			});

			if ( mRunning, {
				// Request the contents of the buffer - no need to resend lost,
				// since we're only interested in the most fresh data
				mBufferRequester.sendAll(mRequest.asArray);
			}, {
				// Resend the final request if it got lost
				if ( mDone.test.not and: (mRequest.duration > lostDuration), {
					mBufferRequester.sendAll(mRequest.asArray);
				});

			});

			if ( mRequest.data.notNil and: mDone.test.not, {
				// Dispatch request data
				var data = mRequest.data;
				var n = cs.nClusters;
				var m = cs.nMetrics;
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

			// Continue if:
			if (mRunning or: mDone.test.not, 3, nil)
		});
	}

	// Free the synths and buffers after finishing fetching data.
	// The synths are guaranteed to be paused at this point - so buffers should be stable.
	stop {
		// Free synths
		mSynth2.free;
		mSynth1.free;

		// Stop fetching data
		// Replace mRequest with a fresh one, to avoid having it overwritten by old requests
		mRequest = mRequest.deepCopy;
		mRequest.data = nil;

		mRunning = false; // Stop fetching data
		mDone.test = false; // Will block on wait

		// Send the request and wait for it to be processed.
		mBufferRequester.sendAll(mRequest.asArray); // Potentially blocking
	}

	sync {
		// Wait for the final request to finish - or don't if mDone.test = false
		// has been executed (when the data has already been fetched), in which case it won't wait.
		mDone.wait;
		mBuffer.free;
	}
}