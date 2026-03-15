// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
GatedDiskOut : UGen {
	*ar { | bufnum, gate, channelsArray |
		^this.multiNewList(['audio', bufnum, gate] ++ channelsArray.asArray)
	}
}
