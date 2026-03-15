// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsVRP {
	// States
	var <>isVisible;
    var <>loadedVRPdata;
	var <>vrpLoaded;
	var <>cycleThreshold;
	var <>clarityThreshold;
	var <>bStacked;
	var <>bSingerMode;
	var <bHzGrid;
	var <>freqGrid;
	var <>wantsContextSave;
	var <>mapSaved;

	*new {
		^super.new.init;
	}

	init {
		clarityThreshold = 0.96;
		cycleThreshold = 1;
		bStacked = true;
		bSingerMode = false;
		bHzGrid = false;
		freqGrid = VRPViewVRP.iMIDI; // = 0
		isVisible = true;
		wantsContextSave = false;
		mapSaved = false;
		vrpLoaded = false;
	}

	setLoadedData { arg newData;
		loadedVRPdata = newData;
		vrpLoaded = true;
	}

	getLoadedData {
		vrpLoaded = false;
		^loadedVRPdata
	}

	/// For backward compatibility ////
	bHzGrid_ { arg bHz;
		bHzGrid = bHz;
		freqGrid = bHz.asInteger;
	}
}