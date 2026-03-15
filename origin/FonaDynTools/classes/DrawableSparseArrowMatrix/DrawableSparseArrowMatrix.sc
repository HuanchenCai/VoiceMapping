/** FUNCTIONALITY REMOVED as of v1.5.6
DrawableSparseArrowMatrix {
	var mValues; // Triplets of x, y, rot

	var mIdx; // Index of the triplet at pos x, y, or nil
	var mVal; // The actual matrix - not used for drawing
	var mCols;
	var mRows;

	*new { | rows, cols |
		^super.new.init(rows, cols);
	}

	init { | rows, cols |
		mCols = cols;
		mRows = rows;

		mValues = List();
		mIdx = Array.fill(mRows * mCols);
		mVal = Array.fill(mRows * mCols);
	}

	put { | row, col, rotation |
		var idx = row * mCols + col;
		var pos = mIdx[ idx ];
		if ( pos.isNil,
			{
				mIdx[ idx ] = mValues.size;
				mValues.add( [row, col, rotation] );
			}, {
				mValues[pos][2] = rotation;
			}
		);

		mVal[ idx ] = rotation;
	}

	at { | row, col |
		^mVal[ row * mCols + col ]
	}

	rows { ^mRows }
	columns { ^mCols }

	draw { | userView, color |
		var b = userView.bounds;
		Pen.use {
			var p1 = Point(-0.5,-0.3);
			var p2 = Point(-0.5, 0.3);
			var p3 = Point(0.5, 0);

			Pen.scale(b.width / (mCols-1), b.height / (mRows-1));
			// Pen.translate(0.5, 0.5);
			Pen.color = color ?? Color.black;
			mValues do: { | triplet |
				var x, y, rot;
				#y, x, rot = triplet;
				Pen.translate(x, y);
				Pen.rotate(rot);
				Pen.moveTo(p1);
				Pen.lineTo(p2);
				Pen.lineTo(p3);
				Pen.fill;
				Pen.rotate(rot.neg);
				Pen.translate(x.neg, y.neg);
			};
		};
	}
}

**/