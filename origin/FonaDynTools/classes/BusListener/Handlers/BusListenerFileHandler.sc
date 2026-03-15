// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
BusListenerFileHandler {
	var mFile;
	var mIndices;
	var mMutex;

	*new { | nBuses, indices, path|
		^super.new.init(nBuses, indices, path);
	}

	init { | nBuses, indices, path |
		mFile = File(path, "w");
		mMutex = Semaphore(1);
		mIndices = indices.copy;

		// Check for invalid indices
		mIndices do: { | i |
			if ( i.inclusivelyBetween(0, nBuses - 1).not, {
				Error("File handler bus index out of bounds!").throw;
			});
		};
	}

	dispatch { | data |
		mMutex.wait;
		data.dataAsFrames do: { | frame |
			frame[mIndices] do: { | value |
				mFile.putString(value.asString ++ " ");
			};
			mFile.putString("\r\n");
		};
		mMutex.signal;
	}

	free {
		mMutex.wait;
		mFile.close;
		mMutex.signal;
	}
}