// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// This is the foundation for the StreamingBuffer class, that handles allocation of the buffer,
// buses, synth and listener. It's a simple manager for these objects, and will issue requests to
// them via the specified clock. The main bulk of the work is done by the Listener and synth.
//
BasicBusListener {
	// Buses
	var mcoBusIndex;
	var miBusGate;
	var mBuses; // The array of buses given as an argument to *new

	// Buffers
	var mBuffer;

	// Targets
	var mTarget;

	// Synths
	var mSynth;

	// Members
	var mBufferSize; // The size of the buffer in # of floats (frames * channels)
	var mClock; // Clock used to schedule fetches
	var mUniqueName; // Unique name for the synth
	var mHelper; // The helper class used to grab data from the server

	var mStop; // True when stop has been called.
	var mAllRequested; // True when all data has been requested after stop was called!
	var mDone; // True if all data has been fetched, and the clock shouldn't reschedule!
	var mCondition; // Signaled when the reading has finished.
	var mRepeat; // True if it should continue reading, false otherwise.

	// Constants
	classvar nBufferMultiplier = 3; // Multiply the expected fetch-size by nBufferMultiplier to estimate the size of the required buffer
	classvar minBufferLength = 2; // At least # seconds worth of buffer

	// Class variables dedicated to generating unique identifiers for the Synths
	classvar cId = 0;
	classvar cPrefix = \streamingbuffer;

	*new {
		^super.new.basicInit;
	}

	basicInit {
		var id;
		// Get a unique identifier
		id = cId;
		cId = cId + 1;
		mUniqueName = cPrefix ++ id.asString;
	}

	prepare { | libname, server, iBusArray, iBusGate, clock |

		// Set the parameters
		mClock = clock;
		miBusGate = iBusGate;
		mBuses = iBusArray;

		// Allocate buffers and buses
		mcoBusIndex = Bus.control(server);
		mcoBusIndex.set(0);
		mBufferSize = ( max(nBufferMultiplier / mClock.tempo, minBufferLength) * server.actualSampleRate ).ceil.asInteger; // # of frames
		mBuffer = Buffer.alloc(server, mBufferSize, mBuses.size);
		mBufferSize = mBufferSize * mBuses.size; // Scale up to the actual size of the buffer

		// format("BufferSize: %", mBufferSize).postln;

		// Init listener
		mHelper = BusListenerHelper(mBuffer);

		// Create the synthdef
		SynthDef(mUniqueName, BasicBusListenerSD.getSynthDef(miBusGate, *mBuses)).add(libname);
	}

	start { | server, target |
		mTarget = target;

		// Start the synth
		mSynth = Synth(mUniqueName,
			BasicBusListenerSD.getSynthArgs(mBuffer, mcoBusIndex, miBusGate, mBuses),
			mTarget, addAction: \addToTail);

		// Reset the variables for the stopping sequence
		mStop = false;
		mAllRequested = false;
		mDone = false;
		mCondition = Condition(true);

		// Start fetching data.
		mClock.sched(1, {
			var ret = 1; // Assume we are not done

			mHelper.resendLost;

			if (mAllRequested.not, { // Check if all data has been requested!

				// Request current position
				mcoBusIndex.get{ | index |
					if (mAllRequested.not, { // Ensure that we don't get here twice!

						// All requested if stop has been called and we're here!
						if (mStop, { mAllRequested = true; });

						mHelper.sendReads(index * mBuses.size);
					}); // End all requested
				}; // End request position

			}); // End Requested all?

			mHelper.dispatch{ | data |
				this.dispatch(BusListenerDataFormatter(data, mBuses.size));
			};

			if (mAllRequested and: mHelper.fetchedAll and: (mHelper.requestsLeft == 0), {
				// All data has been requested, and processed, so we are done!
				ret = nil;
				mCondition.test = true; // Assure that no-one get stuck on wait after we exit here
				mCondition.signal; // Signal anyone who's stuck waiting
			});

			ret
		});

		this
	}

	stop {
		// We can free the synth immediately,
		// but we need to keep the buffer and index bus alive
		// until all data has been fetched from the server.
		mSynth.free;

		if (mHelper.requestsLeft > 2, {
			format("Behind by % requests", mHelper.requestsLeft).postln
		});

		mStop = true;
		mCondition.test = false;

		Routine.run({
			mCondition.wait; // Wait for all of the data to be fetched and dispatched

			mBuffer.free;
			mcoBusIndex.free;
			this.free;

			nil
		}, clock: mClock);
	}

	sync {
		mCondition.wait;
	}

	nBuses {
		^mBuses.size;
	}
}