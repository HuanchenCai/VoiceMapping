// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
BusManager {
	var mDictAudio;
	var mDictControl;
	var mServer;

	*new { | server |
		^super.new.init(server);
	}

	init { | server |
		mServer = server;
		mDictAudio = Dictionary();
		mDictControl = Dictionary();
	}

	// Tell the manager that you require an audio rate bus with at least minChannels channels and give it a name.
	requireAudio { | name, minChannels = 1 |
		var curr = mDictAudio.at(name);
		if (curr.isNil, {
			mDictAudio.put(name, minChannels);
		}, {
			if ( curr < minChannels, {
				mDictAudio.put(name, minChannels);
			});
		});

		this
	}

	// Tell the manager that you require a control rate bus with at least minChannels channels and give it a name.
	requireControl { | name, minChannels = 1 |
		var curr = mDictControl.at(name);
		if (curr.isNil, {
			mDictControl.put(name, minChannels);
		}, {
			if ( curr < minChannels, {
				mDictControl.put(name, minChannels);
			});
		});

		this
	}

	// Get the control rate bus with the given name.
	control { | name |
		var ret = mDictControl.at(name);
		if ( ret.isNil, {
			Error("There is no control rate bus named " ++ name.asString).throw;
		});
		^ret;
	}

	// Get the audio rate bus with the given name.
	audio { | name |
		var ret = mDictAudio.at(name);
		if ( ret.isNil, {
			Error("There is no audio rate bus named " ++ name.asString).throw;
		});
		^ret;
	}

	// Allocate all buses
	allocate {
		mDictAudio keysValuesChange: { | key, value | Bus.audio(mServer, value) };
		mDictControl keysValuesChange: { | key, value | Bus.control(mServer, value) };
	}

	// Free all buses
	free {
		[mDictAudio, mDictControl] do: { | dict | dict do: { | bus | bus.free; }; };
		mDictAudio = Dictionary();
		mDictControl = Dictionary();
	}

	debug {
		"Audio rate buses:".postln;
		mDictAudio associationsDo: { | a |
			a.postln;
		};

		"".postln;
		"Control rate buses:".postln;
		mDictControl associationsDo: { | a |
			a.postln;
		};

	}
}