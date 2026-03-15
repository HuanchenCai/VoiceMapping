// Copyright (C) 2016-2026 by Sten Ternström, Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

BusListenerScopeHandler {
	var mDuration;
	var mIndices;
	var mData;
	var mfOnDispatch;

	*new { | nBuses, indices, duration, fnOnDispatch |
		^super.new.init(nBuses, indices, duration, fnOnDispatch);
	}

	init { | nBuses, indices, duration, fnOnDispatch |
		mDuration = duration;
		mIndices = indices.copy;
		mData = List() ! mIndices.size;
		mfOnDispatch = fnOnDispatch;

		// Check for invalid indices
		mIndices do: { | i |
			if ( i.inclusivelyBetween(0, nBuses - 1).not, {
				Error("Scope handler bus index out of bounds!").throw;
			});
		};
	}

	data { ^mData }

	duration { ^mDuration }

	indices { ^mIndices }

	dispatch { | data |
		var chs = data.dataAsChannels[mIndices];
		var old_last_time, old_last_idx;

		// Guard against nil lists (times?)
		old_last_time = chs.first.last ? mDuration;
		// Remove old
		old_last_idx = SortedAlgorithms.upper_bound( mData.first, old_last_time - mDuration );

		mData do: { | data, idx |
				mData[idx] = data.drop(old_last_idx);
		};

		// Add new
		chs do: { | ch, idx | mData[idx].addAll(ch); };

		// Call the dispatch function and hand it the data
		mfOnDispatch.(mData);
	}
}
