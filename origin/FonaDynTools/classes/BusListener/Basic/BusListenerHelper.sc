// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// A BusListenerHelper, that will handle transferring data between
// the server and client in the most efficient way possible using an implementation
// class to handle the actual sending and splitting of requests.
// Simply put - this class handles _when_ to perform different tasks, rather than
// solving them individually.
//
BusListenerHelper {

	// Reading related members
	var mBufferRequester; // BufferRequester to grab data from the internal buffer
	var mReadingList; // Stores Streaming Buffer Requests
	var mIndexSubmitted; // How far data has been dispatched
	var mIndexReading; // How far reading requests have been initiated

	*new { | buffer |
		^super.new.basicInit( buffer );
	}

	basicInit { | buffer |
		mBufferRequester = BufferRequester(buffer);

		mIndexSubmitted = 0;
		mIndexReading = 0;
		mReadingList = List();
	}

	fetchedAll {
		^( (mIndexSubmitted == mIndexReading) and: (0 == this.requestsLeft));
	}

	resendLost {
		var lostDuration = mBufferRequester.lostDuration, lost = List();
		mReadingList do: { | request |
			if (request.data.isNil and: (request.duration > lostDuration), {
				lost.add(request);
			});
		};

		if (lost.size > 10, { Error("Behind by > 10!").throw; });
		if (lost.notEmpty, { mBufferRequester.sendAll(lost); });

		this
	}

	sendReads { | availableIndex |
		if ( mIndexReading != availableIndex, {
			var available;
			available = mBufferRequester.asRequests(mIndexReading, availableIndex);
			mIndexReading = availableIndex;

			// format("Sending requests:").postln;
			// available do: { | x | x.print; };

			mReadingList.addAll(available);
			mBufferRequester.sendAll(available);
		});

		this
	}

	dispatch { | dispatchFn |
		var dispatch_list = List();

		// Collect the data of all read requests
		// NOTE: We cannot dispatch inside the loop, since the dispatchFn may yield the thread
		// handling this would require a mutex, which may slow down dispatching
		block { | break |
			mReadingList do: { | request |
				if (request.data.isNil, {
					// Not read yet - so break out
					break.value;
				});

				// format("Dispatching: % % %", request.index, request.count, request.data).postln;
				dispatch_list.add(request.data);
				mIndexSubmitted = request.index + request.count;
			};
		};

		// Remove any read requests from the reading list
		mReadingList = mReadingList.drop(dispatch_list.size);

		// Dispatch all read data
		dispatch_list do: { | data | dispatchFn.(data); };
	}

	requestsLeft {
		^mReadingList.size;
	}
}