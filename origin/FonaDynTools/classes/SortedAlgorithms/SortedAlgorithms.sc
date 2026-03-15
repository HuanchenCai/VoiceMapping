// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
//
// Algorithms that can be applied to sorted ranges
//
SortedAlgorithms {

	classvar <functor_less;
	classvar <functor_greater;

	*initClass {
		functor_less = { | a, b | a < b };
		functor_greater = { | a, b | a > b };
	}

	*lower_bound { | seq, elem, firstIdx = nil, lastIdx = nil, pred = nil |
		var middle;
		firstIdx = (firstIdx ?? 0).asInteger;
		lastIdx = (lastIdx ?? seq.size).asInteger;
		pred = pred ?? { this.functor_less };

		while ({ firstIdx != lastIdx }, {
			middle = (lastIdx - firstIdx).half.asInteger + firstIdx;
			if ( pred.(seq[middle], elem), {
				firstIdx = middle + 1; // upper half
			}, {
				lastIdx = middle; // lower half, or middle
			});
		});

		^firstIdx;
	}

	*upper_bound { | seq, elem, firstIdx = nil, lastIdx = nil, pred = nil |
		var middle;
		firstIdx = (firstIdx ?? 0).asInteger;
		lastIdx = (lastIdx ?? seq.size).asInteger;
		pred = pred ?? { this.functor_less };

		while ({ firstIdx != lastIdx }, {
			middle = (lastIdx - firstIdx).half.asInteger + firstIdx;
			if ( pred.(elem, seq[middle]) , {
				lastIdx = middle; // lower half, or middle
			}, {
				firstIdx = middle + 1; // Upper half
			});
		});

		^firstIdx;
	}

	*equal_bound { | seq, elem, firstIdx = nil, lastIdx = nil, pred = nil |
		firstIdx = (firstIdx ?? 0).asInteger;
		lastIdx = (lastIdx ?? seq.size).asInteger;
		pred = pred ?? { this.functor_less };
		^[
			this.lower_bound(seq, elem, firstIdx, lastIdx, pred),
			this.upper_bound(seq, elem, firstIdx, lastIdx, pred)
		];
	}
}