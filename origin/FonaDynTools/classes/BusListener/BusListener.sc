// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
BusListener : BasicBusListener {

	var mHandlers;
	var mHandlerConstructors; // Functions constructing the actual handlers

	classvar cDictHandlers;

	*new {
		^super.new.init;
	}

	init {
		mHandlers = Dictionary();
		mHandlerConstructors = Dictionary();

		this
	}

	// Instantiates an assignment tool that helps with assigning indices to buses
	*newBusAssignmentTool {
		var tool = {
			var mDict = Dictionary(); // Mapping: \Name -> Indices
			var mAudioIndex = Dictionary(); // Mapping: bus.index -> Index
			var mControlIndex = Dictionary(); // Mapping: bus.index -> Index
			var mBuses = List(); // List of all buses
			(
				// Makes room for the buses, and gives them a name that can be used to
				// fetch their indices
				assign:
				{ | fn, name, buses |
					var indices = buses.asArray collect: {
						| bus |

						var isAudio = bus.rate == \audio;
						var indices =
						bus.numChannels.asInteger collect: { | chidx |
							var busidx = bus.index + chidx;
							var idx =
							if ( isAudio,
								{ mAudioIndex[busidx] },
								{ mControlIndex[busidx] }
							);

							if ( idx.isNil, {
								// Do not have this bus - so add it
								mBuses.add( bus.subBus(chidx) );
								idx = mBuses.size - 1;

								if ( isAudio,
									{ mAudioIndex.put(busidx, idx); },
									{ mControlIndex.put(busidx, idx); }
								);
							});

							idx
						};

						indices
					};

					mDict.put(name, indices.flat);
				},

				// Grabs the indices associated with the name of the buses assigned via assign
				// These indices can be given to any of the handlers
				indices:
				{ | fn, name |
					mDict[name]
				},

				// Grabs an array of all buses - to give to prepare
				buses:
				{
					mBuses.asArray
				}
			)
		};

		^tool.();
	}

	*initClass {
		cDictHandlers = Dictionary.newFrom([
			\soundfile,
			{ | sb ...args |
				BusListenerSoundFileHandler(sb.nBuses, *args)
			}, // args: indices, path, headerFormat, sampleFormat = "int16"

			\plot,
			{ | sb ...args |
				BusListenerPlotHandler(sb.nBuses, *args);
			}, // args: indices

			\file,
			{ | sb ...args |
				BusListenerFileHandler(sb.nBuses, *args);
			}, // args: indices, path

			\scope,
			{ | sb ...args |
				BusListenerScopeHandler(sb.nBuses, *args);
			}, // args: indices, duration, Function taking a matrix with the
			   // current scope data with the timestamp channel first, followed by the data from all buses as channels
			   // NOTE: The timestamp MUST be the first index in indices!

			\custom,
			{ | sb ...args |
				BusListenerCustomHandler(*args);
			} // args: Function taking a BusListenerDataFormatter
		]);
	}

	addHandler { | name, type ...args |
		mHandlerConstructors.add( name.asSymbol -> { cDictHandlers.at(type.asSymbol).(this, *args) } );
	}

	handler { | name |
		^mHandlers[name.asSymbol]
	}

	prepare { | libname, server, iBusArray, iBusGate, clock |
		super.prepare(libname, server, iBusArray, iBusGate, clock);

		mHandlerConstructors associationsDo: { | a |
			mHandlers.put( a.key, a.value.() );
		};
	}

	start { | server, target |
		super.start(server, target);
	}

	stop {
		super.stop;
	}

	sync {
		super.sync;
	}

	dispatch { | data |
		mHandlers do: { | handler | handler.dispatch(data); };

		this
	}

	free {
		mHandlers do: { | handler | handler.free; };

		this
	}
}