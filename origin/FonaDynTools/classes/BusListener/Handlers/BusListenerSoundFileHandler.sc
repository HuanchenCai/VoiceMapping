// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
BusListenerSoundFileHandler {
	var mFile;
	var mIndices;
	var mMutex;

	*new { | nBuses, indices, path, headerFormat, sampleFormat = "int16" |
		^super.new.init(nBuses, indices, path, headerFormat, sampleFormat);
	}

	init { | nBuses, indices, path, headerFormat, sampleFormat |
		mFile = SoundFile.new.headerFormat_(headerFormat).sampleFormat_(sampleFormat).numChannels_(indices.size);
		mFile.openWrite(path);

		mIndices = indices.copy;
		mMutex = Semaphore(1);

		// Check for invalid indices
		mIndices do: { | i |
			if ( i.inclusivelyBetween(0, nBuses - 1).not, {
				Error("Soundfile handler bus index out of bounds!").throw;
			});
		};
	}

	dispatch { | data |
		mMutex.wait;
		data.dataAsFrames do: { | frame |
			mFile.writeData( FloatArray.with(*frame[mIndices]) );
		};
		mMutex.signal;
	}

	free {
		mMutex.wait;
		mFile.close;
		mFile.free;
		mMutex.signal;
	}
}