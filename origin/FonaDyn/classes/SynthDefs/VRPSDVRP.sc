// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //


Dolansky {
	*ar { arg in, decay, coeff;
		var peakPlus  = FOS.ar(PeakFollower.ar(in.max(0), decay), coeff, coeff.neg, coeff);
		var peakMinus = FOS.ar(PeakFollower.ar(in.neg.max(0), decay), coeff, coeff.neg, coeff);
		^Trig1.ar(SetResetFF.ar(peakPlus, peakMinus), 0);
	}
}

// This pseudo-UGen for the crest factor is cycle-synchronous
// and more correct than the built-in Crest UGen.
CrestCycles {
	*ar { arg in;
		var rms, trig, out;

		trig = Dolansky.ar(in, 0.999, 0.99);
		rms = AverageOut.ar(in.squared, trig).sqrt;
		out = RunningMax.ar(in.abs, Delay1.ar(trig))/rms;
		^[rms, Latch.ar(out, trig)]
	}
}

SpectrumBalance {
	*ar { arg in;
		var levelLo, levelHi;
		levelLo = RMS.ar(BLowPass4.ar(in, 1500, 2), 50).ampdb;
		levelHi = RMS.ar( BHiPass4.ar(in, 2000, 2), 50).ampdb;
		^Sanitize.ar(levelHi-levelLo, -50.0);
	}
}



VRPSDVRP {
	classvar nameAnalyzeAudio = \sdAnalyzeAudio;
	classvar nameAnalyzeAudio2 = \sdAnalyzeAudio2;
	classvar nameCPPsmoothed = \sdCPPsmoothed;
	// classvar nameCorrVoiceEGG = \sdCorrVoiceEGG;

	*compile { | libname, bSmoothCPP=true |

		///////////////////////////////////////////////////////////////////////////////////////////////////////
		// Analyze Audio SynthDef
		///////////////////////////////////////////////////////////////////////////////////////////////////////  ;
		SynthDef.new(nameAnalyzeAudio,
			{ | aiBusConditionedMic,
				coBusFrequency,
				coBusAmplitude,
				coBusClarity,
				coBusCrest,
				coBusSB |

				var in, inrms, amp, freq, freqOut, crest, gate, clarity, specBal;

				in = In.ar(aiBusConditionedMic);
				#inrms, crest = CrestCycles.ar(in);
				specBal = SpectrumBalance.ar(in);

				// The following line serves only to guard against true-zero audio in test files
				amp = Select.kr(InRange.kr(inrms, -1.0, 0.0), [inrms.ampdb, DC.kr(-100)]);

				// Integrator brings down the HF - but is that needed?
				# freq, clarity = Tartini.kr(Integrator.ar(in, 0.995), n: 2048, k: 0, overlap: 1024);
				freq = Sanitize.kr(freq.cpsmidi, 20);

				Out.kr(coBusFrequency, [freq]);
				Out.kr(coBusAmplitude, [amp]);
				Out.kr(coBusClarity, [clarity]);
				Out.kr(coBusCrest, [crest]);
				Out.kr(coBusSB, [specBal]);
			}
		).add(libname);


		/////////////////////////////////////////////////////////////////////////////////////////////////////
		// Cepstral Peak Prominence SynthDef
		/////////////////////////////////////////////////////////////////////////////////////////////////////

		SynthDef.new( nameCPPsmoothed,
			{ | aiBusConditionedMic,
				coBusCPPsmoothed |

				var in, inWithDither, chain, cepsChain, fftBuffer, cepsBuffer;
				var cpp, cppSan, slope, intercept, maxcpp, maxix;
				var lowBin = 25, highBin = 367;  // 880 Hz down to 60 Hz
				var ditherAmp = 1000000.reciprocal;		// was 24000.reciprocal until v3.0.6d

				fftBuffer = LocalBuf(2048);		// Tried halving the bufsize but not good
				cepsBuffer = LocalBuf(1024);

				in = In.ar(aiBusConditionedMic, 1);			// Get the audio signal
				inWithDither = WhiteNoise.ar(ditherAmp, add: in);// Prevent divide-by-zero issues later in the chain
				chain = FFT(fftBuffer, inWithDither, wintype: 1);  // Hanning window
				cepsChain = Cepstrum(cepsBuffer, chain);	// Both buffers are now in polar form (mag,phase)
				if (bSmoothCPP, {
					cepsChain = PV_MagSmooth(cepsChain, 0.3);	// Approx 16 Hz LP1 filter
					cepsChain = PV_MagSmear(cepsChain, 3);		// Implements 7-bin smearing (+/- 3 bins mean)
				});

				// PeakProminence is a custom UGen that is provided with FonaDyn
				// Only the cpp result is used here
				#cpp, slope, intercept, maxcpp, maxix = PeakProminence.kr(cepsChain, lowBin, highBin);
				cppSan = Sanitize.kr(cpp, -1.0);
				// cppSan = VarLag.kr(cppSan, 0.02322, 0, \lin);		// new in 3.3.0
				Out.kr(coBusCPPsmoothed, [cppSan]);
			}
		).add(libname);

/*		////////////////////////////////////////////
		///// Experimental computation of Voice-EGG correlation
		////////////////////////////////////////////

		SynthDef.new(nameCorrVoiceEGG,
			{ | aiBusConditionedMic,
				ciChain,
				coBusMaxCorr,
				coBusIxDelay |

			var chain, chainEGG, chainMic, fBuffer;
			var micSignal, corrSignal, rmsCorr;
				// var minCorr, maxCorr, ixDelay;
			var bufSize = 2048;

			fBuffer = LocalBuf(bufSize);

			// The LPF will introduce a varying group delay,
			// it might need to be a FIR if we are going to use the ixDelay result
			micSignal = LPF.ar(In.ar(aiBusConditionedMic, 1), freq: 250.0, mul: -10.0);  // which mul polarity?

			chainEGG = In.kr(ciChain, 1);					// Get the EGGcond spectrum buffer
			chainMic = FFT(fBuffer, micSignal);				// FFT the mic signal
			chainMic = PV_Conj(chainMic);					// Take the complex conjugate
			chain = PV_Mul(chainMic, chainEGG);				// Multiply the spectra
			corrSignal = IFFT.ar(chain, wintype: 0);		// -1: No windowing of the correlation "signal"
			rmsCorr = MovingAverage.rms(corrSignal, numsamp: 1000, maxsamp: bufSize/2);
			Out.kr(coBusMaxCorr, [rmsCorr]);
				// Out.kr(coBusIxDelay, [ixDelay]);
			Poll.kr(Impulse.kr(10), rmsCorr, "rmsCorr");
				// Poll.kr(Impulse.kr(10), ixDelay, "ixDelay");
		}
		).add(libname);
*/
	} // .compile




	*analyzeAudio { | aiBusConditionedMic, coBusFrequency, coBusAmplitude, coBusClarity, coBusCrest, coBusSB ...args |
		^Array.with(nameAnalyzeAudio,
			[
				\aiBusConditionedMic, aiBusConditionedMic,
				\coBusFrequency, coBusFrequency,
				\coBusAmplitude, coBusAmplitude,
				\coBusClarity, coBusClarity,
				\coBusCrest, coBusCrest,
				\coBusSB, coBusSB
			],
			*args
		);
	}

	*cppSmoothed { | aiBusConditionedMic, coBusCPPsmoothed ...args |
		^Array.with(nameCPPsmoothed,
			[
				\aiBusConditionedMic, aiBusConditionedMic,
				\coBusCPPsmoothed, coBusCPPsmoothed
			],
			*args
		);
	}

/*	*corrVoiceEGG { | aiBusConditionedMic, ciChain, coBusMaxCorr, coBusIxDelay ...args |
		^Array.with(nameCorrVoiceEGG,
			[
				\aiBusConditionedMic, aiBusConditionedMic,
				\ciChain, ciChain,
				\coBusMaxCorr, coBusMaxCorr,
				\coBusIxDelay, coBusIxDelay
			],
			*args
		);

	}
*/
}