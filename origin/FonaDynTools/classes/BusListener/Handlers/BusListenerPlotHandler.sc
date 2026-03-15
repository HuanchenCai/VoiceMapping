// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
BusListenerPlotHandler {
	var mFrames;
	var mIndices;
	var mData;
	var mMutex;
	var mTitle;

	*new { | nBuses, indices, title |
		^super.new.init(nBuses, indices, title);
	}

	init { | nBuses, indices, title |
		mFrames = 0;
		mIndices = indices.copy;
		mData = { List() } ! mIndices.size;
		mMutex = Semaphore(1);
		mTitle = title;

		// Check for invalid indices
		mIndices do: { | i |
			if ( i.inclusivelyBetween(0, nBuses - 1).not, {
				Error("Plot handler bus index out of bounds!").throw;
			});
		};
	}

	dispatch { | data |
		mMutex.wait;
		data.dataAsChannels[mIndices] do: { | channel, idx |
			mData[idx].addAll(channel);
		};
		mMutex.signal;
	}

	free {
		mMutex.wait;
		{ mData.plot(mTitle) }.defer;
		mMutex.signal;
	}
}