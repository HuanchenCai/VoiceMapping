// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
GatedBufWr : UGen {
	*kr { | inputArray, bufnum, gate, phase, loop = 1 |
		^this.multiNewList( ['control', bufnum, gate, phase, loop] ++ inputArray );
	}
}