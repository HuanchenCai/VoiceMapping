// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// Three different implementation classes for grabbing information from a Buffer on the server, that each perform 2 tasks:
// 1) Splitting a long request into suitable requests for the method used.
// 2) Sending the actual request to the server, and placing the result of the request into the requests data member.
//

//
// A simple class that contains all information required for requests.
//
BufferRequest {
	var <index; // The starting index of the read (into the buffer)
	var <count; // The # of requested floats
	var <timestamp; // When the request was sent
	var <>data; // The data if read, nil otherwise

	*new { | idx, cnt |
		^super.newCopyArgs(idx, cnt, nil, nil);
	}

	// Request how old the request is (since it was sent) - doesn't handle failure
	duration {
		^(this.class.now() - timestamp);
	}

	updateTimestamp {
		timestamp = this.class.now();
		this
	}

	*now {
		^Process.elapsedTime;
	}
}

//
// BufferRequester, that simply redirects to the most suitable implementation given the buffer.
//
BufferRequester {
	*new { | buffer |
		var impl =
		if ( buffer.server.isLocal and:
			((buffer.numFrames * buffer.numChannels) > BufferRequesterGetn.nMaxRead),

			BufferRequesterMultiLoadToFloatArray,
			BufferRequesterGetn
		);

		^impl.new(buffer);
	}

	// To allow the documentation to see them
	buffer {}
	asRequests { | from, to | }
	sendAll { | requestContainer | }
	lostDuration { }
}

//
// An entry manager for the BufferRequesterGetn implementation. It handles pushing entries at the back quickly, as well as locating requests and removing old ones.
//
BufferRequesterGetnEntryManager {
	var mArr;
	var mIdxFirst;
	var mIdxLast;
	var mLatency;

	*new { | latency, size = 128 |
		^super.new.init(latency, size);
	}

	init { | latency, size |
		mArr = Array.newClear(size);
		mIdxFirst = 0;
		mIdxLast = 0;
		mLatency = latency;
	}

	//
	// Sets the data member of the first request with the given index and count. Also removes old requests.
	//
	setData { | index, count, data |
		var oldUntil = mIdxFirst;
		block { | break |
			var oldBefore = BufferRequest.now() - mLatency;

			// Walk through all valid indices
			forBy(mIdxFirst, mIdxLast - 1, 1, { | i |
				var entry = mArr.wrapAt(i); // Need to use wrapAt since we're never wrapping the indices

				// If it is nil it has already been handled
				if ( entry.notNil, {
					// Correct count & index?
					if ( (entry.count == count) and: (entry.index == index), {
						// Found a matching request so update its data and set mArr[i] = nil
						entry.data = data;
						mArr.wrapPut(i, nil);
						break.value;
					});

					// If this request is old we can throw away all entries earlier than this one.
					if ( entry.timestamp < oldBefore, {
						oldUntil = i;
					});
				}, {
						// If we could throw away the previous request, we can throw away this one too
						// since it has already been handled (and thus set to nil)
						if (oldUntil == (i - 1), {
							oldUntil = i;
						});
				});
			});
		};

		// Update mIdxFirst (i.e. removing handled or old requests)
		mIdxFirst = oldUntil;
		this
	}

	add { | request |
		// Check if we're overwriting a valid request in mArr
		if ( (mIdxLast - mIdxFirst) > mArr.size, {
			Error("BufferRequesterGetn gets more requests than it can handle!");
		});

		// With a 32 bit floating point or 32 bit integer it would take more than 2**24 (~16.8 million) requests before the indices become faulty.
		// Assuming 1000 requests/second it would take almost 5 hours to use up all these indices.
		mArr.wrapPut(mIdxLast, request.updateTimestamp);
		mIdxLast = mIdxLast + 1;
	}
}

//
// An implementation class for the BufferRequester, that uses Buffer.getn to retrieve
// data from the server. This is the only way for a remote server to send data to the client.
//
BufferRequesterGetn {
	var <buffer;
	var mEM; // The BufferRequesterGetnEntryManager for this buffer

	classvar <nMaxRead = 1633; // Maximum amount of floats to read at a time

	classvar sBuffers; // A list with references to all sBuffers
	classvar sOSCFuncs; // A list with OSCFuncs for each server
	classvar sEntryManagers; // BufferRequesterGetnEntryManager for each buffer

	*initClass {
		sBuffers = List();
		sOSCFuncs = List();
		sEntryManagers = List();

		// Clear the lists when Cmd + Period is used ("stop all").
		CmdPeriod.add(this);
	}

	*getIndex { | buffer, lostDuration |
		var idx = sBuffers.indexOf(buffer);
		if (idx.isNil, {
			if ( buffer.notNil, {
				var em;
				idx = sBuffers.size;
				sBuffers.add(buffer); // Keep track of the buffer to locate the index later

				// Create an entry manager and store it at the same index
				em = BufferRequesterGetnEntryManager(lostDuration);
				sEntryManagers.add(em);

				// Init an OSCFunc to grab all responses to '/b_getn' for this buffer.
				sOSCFuncs.add(
					OSCFunc({ | msg |
						var idx = msg[2];
						var count = msg[3];
						var data = msg.copyToEnd(4);
						em.setData(idx, count, data);
					}, '/b_setn', buffer.server.addr, nil, [buffer.bufnum])
				);
			});
		});
		^idx;
	}

	*cmdPeriod {
		this.clear();
	}

	*clear {
		sBuffers.clear();
		sOSCFuncs.clear();
		sEntryManagers.clear();
	}

	*new { | buffer |
		^super.new.init(buffer);
	}

	lostDuration {
		^ (buffer.server.latency * 3) ;
	}

	init { | buf |
		buffer = buf;
		mEM = sEntryManagers[ BufferRequesterGetn.getIndex(buf, this.lostDuration) ]; // Exception if buf.isNil
	}

	asRequests { | from, to |
		var nChannels = buffer.numChannels;
		var bufsize = nChannels * buffer.numFrames;
		var ret = List();
		var maxread = (nMaxRead / nChannels).asInteger * nChannels;
		if ( from > to, {
			// Wrapping
			while ({from != bufsize}, {
				var count = min(maxread, bufsize - from);
				ret.add(BufferRequest(from, count));
				from = from + count;
			});

			from = 0;
		});

		while ({from != to}, {
			var count = min(maxread, to - from);
			ret.add(BufferRequest(from, count));
			from = from + count;
		});

		^ret;
	}

	sendAll { | requestContainer |
		// Send all '/b_getn' messages to the server as a bundle.
		buffer.server.listSendBundle(nil,
			requestContainer collect: {
				| request |
				mEM.add(request);
				buffer.getnMsg(request.index, request.count)
			}
		);
	}
}


//
// An implementation class for the BufferRequester, that uses Buffer.loadToFloatArray to retrieve
// data from the server. This method only works with an internal or local server. It has one major flaw
// as there is no way for it to differentiate between requests on the same buffer. Hence only one request
// on the same buffer at a time is valid.
//
BufferRequesterLoadToFloatArray {
	var <buffer;

	*new { | buffer |
		^super.new.init(buffer);
	}

	lostDuration {
		^ (buffer.server.latency * 2) ;
	}

	init { | buf |
		buffer = buf;
	}

	asRequests { | from, to |
		var nChannels = buffer.numChannels;
		var bufsize = nChannels * buffer.numFrames;
		var ret = List(2);
		if (from > to, {
			// Wrapping
			var count = bufsize - from;
			if (0 != count, {
				ret.add( BufferRequest(from, count) );
			});
			from = 0;
		});

		ret.add( BufferRequest(from, to - from) );
		^ret;
	}

	sendAll { | requestContainer |
		requestContainer do: { | request | this.send(request); };
	}


	send { | request |
		request.updateTimestamp;
		buffer.loadToFloatArray(request.index, request.count, { | data | request.data = data; });
	}
}

//
// An implementation class for the BufferRequester, that behaves similarly to
// BufferRequesterLoadToFloatArray to retrieve data from the server. The main difference is that
// this implementation will allow multiple requests at the same time, which is a big issue
// for BufferRequesterLoadToFloatArray. Note that even this implementation is unable to know the difference
// between two requests starting at the same index.
//
BufferRequesterMultiLoadToFloatArray {
	var <buffer;
	var <serverLatencyMultiplier = 2; // latency * serverLatencyMultiplier = lostDuration

	*new { | buffer |
		^super.new.init(buffer);
	}

	lostDuration {
		^ (buffer.server.latency * 2) ;
	}

	init { | buf |
		buffer = buf;
	}

	asRequests { | from, to |
		var nChannels = buffer.numChannels;
		var bufsize = nChannels * buffer.numFrames;
		var ret = List(2);
		if (from > to, {
			// Wrapping
			var count = bufsize - from;
			if (0 != count, {
				ret.add( BufferRequest(from, count) );
			});
			from = 0;
		});

		ret.add( BufferRequest(from, to - from) );
		^ret;
	}

	sendAll { | requestContainer |
		var base_path, paths, msgBundle, files,
		c = Condition.new,
		server = buffer.server;

		// Generate unique paths for the temporary files
		// base_path = PathName.tmp ++ this.hash.asString;
		// base_path = PathName.tmp +/+ "tmp" +/+ this.hash.asString;
		base_path = Platform.userAppSupportDir +/+ "tmp" +/+ this.hash.asString;
		paths = requestContainer collect: { | request |
			request.updateTimestamp;
			(base_path ++ "_" ++ request.index.asString ++ "_" ++ request.count.asString)
		};

		// Generate a bundle of writes, send these to the server and wait for them to complete
		msgBundle = paths collect: { | path, idx |
			var request = requestContainer[idx];
			var chs = buffer.numChannels;
			var count = request.count / chs;
			var index = request.index / chs;

			// In the remote chance that it already exists - delete it
			if ( File.exists(path), { File.delete(path); });

			buffer.writeMsg(path, "aiff", "float", count, index)
		};

		{
			server.sync(c, msgBundle);

			// Walk through and read each of the files, and set the data for each request
			paths do: { | path, idx |
				block { | break |
					var file = SoundFile.new, array;
					var request = requestContainer[idx];
					protect {
						if ( file.openRead(path).not, {
							break.value; // Failed read
						});

						if ( (file.numFrames * file.numChannels) == request.count, {
							// Read the data
							array = FloatArray.newClear(file.numFrames * file.numChannels);
							file.readData(array);
							request.data = array;

						}); // else - failed read
					} {
						file.close;
						if(File.delete(path).not) { ("Could not delete data file:" + path).warn };
					};
				};
			};
		}.forkIfNeeded;
	}
}