#!/usr/bin/python
# -*- coding: utf-8 -*-

# based on http://www.rows.ws/jpihack/ and https://github.com/wannamak/edmtools 


from datetime import datetime
from datetime import timedelta
import struct
import sys
import os

# Vendored from https://github.com/2sec/python-edm @ c790955.
# See ATTRIBUTION.md for the list of modifications vs upstream.

# see **NEW** comments below
def isF(flags): return (flags >> 28) & 1


class EDMFlight(object):

    def __init__(self, fnum, date, flags, isF, interval_secs):
        self.fnum = fnum
        self.date = date
        self.flags = flags
        self.isF = isF
        self.interval_secs = interval_secs



class EDMData(object):

    def __init__(self, fileName, outDir=None):
        self.fileName = fileName
        self.outDir = outDir
        # Decoded rows live here after parseFlights() runs:
        #   self.flight_rows[fnum] = list[dict]
        self.flight_rows = {}

    def read(self):
        self.header = None
        self.offset = 0
        with open(self.fileName, "rb") as f: self.data = f.read()

    def loadBytes(self, raw):
        """Alternative to read() when the .JPI content is already in memory
        (e.g. from a web upload). fileName is used only for display."""
        self.header = None
        self.offset = 0
        self.data = raw


    def parseHeader(self):
        data = self.data

        '''
there are new fields since the original version from 2008 (jpihack.cpp), from which most of the comments below are extracted.
I marked them as **NEW** - they are returned by my EDM830 which I purchased in Dec 2020 (current version 7998-2011.06)

    
Header records are "$X,....*NN\r\n" where X is a letter for a record type, and
header records are just text lines delimited by line feeds. Most are series of
numeric short values just converted to comma delimited ascii.

Header records all end in "*NN", where the NN is two hex digits. It is a
checksum, computed by a byte which is the XOR of all the bytes in the header
line excluding the initial '$' and trailing '*NN'.

$L = last header record
        '''

        i = 0 # current position within the buffer being parsed
        header = {}
        flights = []
        atEnd = False

        while not atEnd:
            assert(data[i] == ord('$'))

            # extract field
            j = i
            while(data[i] != 0x0D): i += 1

            line = data[j:i].decode("ascii")

            i += 1
            assert(data[i] == 0x0A)
            i += 1


            # calculate checksumn
            calc = 0

            checksumIndex = 1
            while(line[checksumIndex] != '*'):
                calc ^= ord(line[checksumIndex])
                checksumIndex += 1

            checksum = int(line[checksumIndex + 1:], 16)
            assert(checksum == calc)

            # extract key and value
            line = line[1: checksumIndex]
            key, value = line.split(',', 1)
            value = value.strip(' ')

            atEnd = (key == 'L')

            # $D = flight info, they all have the same letter hence they are appended to a different list
            if key == 'D':
                flights.append(value)
            else:
                header[key] = value


        self.offset = i



   
        cfg = {}

        '''
        $U = tail number
        "$U,N12345_*44"
        '''
        cfg['TAIL NO'] = header['U']

        # helper function used to convert list of integers
        def intLimits(key):
            limits = header[key]
            limits = limits.split(',')
            limits = [int(limit) for limit in limits]
            return limits


        '''
        $A = configured limits:
        VoltsHi*10,VoltsLo*10,DIF,CHT,CLD,TIT,OilHi,OilLo
        "$A,305,230,500,415,60,1650,230,90*7F"
        '''
        limits = intLimits('A')
        cfg['VOLTS LIMIT HIGH'] = limits[0] / 10.0
        cfg['VOLTS LIMIT LOW'] = limits[1] / 10.0
        cfg['EGT SPAN DIF'] = limits[2]
        cfg['HIGH CHT TEMP'] = limits[3]
        cfg['SHOCK COOLING CLD'] = limits[4]
        #cfg['HIGH TIT TEMP'] = limits[5]

        cfg['OIL-T LIMIT HIGH'] = limits[6]
        cfg['OIL-T LIMIT LOW'] = limits[7]

        '''
        $F = Fuel flow config and limits
        empty,full,warning,kfactor,kfactor
        **NEW** 'warning' field seems to be AUX tank capacity instead
        "$F,0,999, 0,2950,2950*53"
        '''
        limits = intLimits('F')
        cfg['FUEL EMPTY'] = limits[0]
        cfg['MAIN TANK SIZE'] = limits[1]
        cfg['AUX TANK SIZE'] = limits[2]
        cfg['K-FACTOR 1'] = limits[3] / 100.0
        cfg['K-FACTOR 2'] = limits[4] / 100.0
        
        
        '''
        $T = timestamp of download, fielded (Times are UTC)
        MM,DD,YY,hh,mm,?? maybe some kind of seq num but not strictly sequential?
        "$T, 5,13, 5,23, 2, 2222*65"
        '''
        limits = intLimits('T')
        mo, d, y, h, mi = limits[0], limits[1], limits[2] + 2000, limits[3], limits[4]
        cfg['DOWNLOAD DATE TIME'] = datetime(y, mo, d, h, mi)
        cfg['LAST FLIGHT NO'] = limits[5]


        '''
        $C = config info (only partially known)
        model#,feature flags lo, feature flags hi, unknown flags,firmware version
        "$C, 700,63741, 6193, 1552, 292*58"

        The feature flags is a 32 bit set of flags as follows:

        // -m-d fpai r2to eeee eeee eccc cccc cc-b
        //
        // e = egt (up to 9 cyls)
        // c = cht (up to 9 cyls)
        // d = probably cld
        // b = bat
        // o = oil
        // t = tit1
        // 2 = tit2
        // a = OAT
        // f = fuel flow
        // r = CDT (also CARB - not distinguished in the CSV output)
        // i = IAT
        // m = MAP
        // p = RPM
        // *** e and c may be swapped (but always exist in tandem)
        // *** d and b may be swapped (but seem to exist in tandem)
        // *** m, p and i may be swapped among themselves, haven't seen
        //     enough independent examples to know for sure.

        **NEW** I think d (bit 29) is ENGINE TEMPS UNIT (1=F) as I compared two saved configurations with this change and it was the only difference


        '''
        limits = intLimits('C')
        cfg['EDM TYPE'] = limits[0]
        flags = limits[1] | (limits[2] << 16)
        cfg['FLAGS'] = flags #'{0:0b}'.format(flags)

        cfg['ENGINE TEMPS UNIT'] = 'F' if isF(flags) else 'C'

        n = len(limits)
        cfg['VERSION'] = limits[n - 1 ] / 10.0 + limits[n - 2]
                
        for i in range(3, n - 2):
            cfg['UNKNOWN C' + str(i)] = limits[i]


        '''
        **NEW**
        $P = CARB  (wild guess)
        1 – lowest Fuel Flow filter
        2 – medium Fuel Flow filter
        3 – highest Fuel Flow filter        
        '''
        cfg['CARB'] = int(header['P'])


        '''
        $D = flight info
        flight#, length of flight's data in 16 bit words
        "$D,  227, 3979*57"

        there's one line per flight
        '''
        for i, flight in enumerate(flights):
            flight = flight.split(',')
            flight = [int(item) for item in flight]
            flight[1] *=  2 # flight data length in bytes
            flights[i] = flight


        '''
        unknown meaning
        $H = 0 
        $L = last header record
        "$L, 49*4D"
        '''

        self.header = header
        self.config = cfg
        self.flights = flights



    def parseFlights(self, additional_columns):

        '''
The flight header follows immediately after the $L record, and is as follows:

struct flightheader {
   ushort flightnumber;  // matches what's in the $D record
   ulong flags;          // matches the "feature flags" in the $C record
   ushort unknown;       // may contain flags about what units (e.g. F vs. C)
   ushort unknown2[7];   // **NEW** I hope there is some sort of a header version somewhere!
   ushort interval_secs; // record interval, in seconds (usually 6)
   datebits dt;          // date as fielded bits, see struct below
   timebits tm;          // time as fielded bits, see struct below
};

The datebits/timebits are bit fields as follows:

// pack a date into 16 bits
struct datebits {
   unsigned day:5;
   unsigned mon:4;
   unsinged year:7;
};

struct timebits {
   unsigned secs:5;      // #secs / 2 is stored
   unsigned mins:6;
   unsigned hrs:5;
};
        '''

        data = self.data
        flights = self.flights

        struct_flightheader = struct.Struct('!14H')

        for i, flight in enumerate(flights):

            # read flightheader
            fnum = flight[0]
            flen = flight[1]
            header = struct_flightheader.unpack_from(data, self.offset)

            if header[0] != fnum:
                self.offset -= 1
                header = struct_flightheader.unpack_from(data, self.offset)


            flags = header[1] | (header[2] << 16)

            assert(header[0] == fnum)

            interval_secs = header[11]


            # read date and time
            def andShift(v, i): return v & (2**i - 1), v >> i

            date = header[12]
            d, date = andShift(date, 5)
            mo, date = andShift(date, 4)
            y = date + 2000

            time =  header[13]
            s, time = andShift(time, 5)
            mi, time = andShift(time, 6)
            h = time
            
            date = datetime(y, mo, d, h, mi, s * 2)


            # read flight data

            flightdata = data[self.offset+struct_flightheader.size:self.offset+flen]

            # debug - save flight data
            # with open(self.fileName + '-' + str(fnum), 'wb') as f: f.write(flightdata)

            # Modified vs upstream: keep raw Fahrenheit on F-native units (FlySto CSV uses F).
            # Setting this to True restores the upstream behaviour of converting to Celsius.
            convertEngineTemp = False

            # no idea where the unit is given in the header! I'll test when needed
            convertOilTemp = False


            if convertEngineTemp:
                convertEngineTemp = isF(flags)

            # GPS extraction (added — see ATTRIBUTION.md): initial position is
            # stored in header words 6-9 as two signed 32-bit ints, decimal
            # degrees × 6000. Zero = no GPS lock in the header.
            def _s32(v):
                return v - 0x100000000 if v > 0x7fffffff else v
            lat_raw = _s32((header[6] << 16) | header[7])
            lng_raw = _s32((header[8] << 16) | header[9])
            initial_lat = lat_raw / 6000 if lat_raw != 0 else None
            initial_lng = lng_raw / 6000 if lng_raw != 0 else None

            self.parseFlight(fnum, flightdata, date, interval_secs, convertEngineTemp, convertOilTemp, additional_columns,
                             initial_lat, initial_lng)

            flights[i] = EDMFlight(fnum, date, flags, 'C', interval_secs)

            self.offset += flen






    def parseFlight(self, fnum, data, date, interval_secs, convertEngineTemp, convertOilTemp, additional_columns,
                    initial_lat=None, initial_lng=None):

        # Modified vs upstream: silenced print; rows are captured in self.flight_rows
        # and only written to disk if self.outDir was provided.
        rows = []

        # GPS state (added — see ATTRIBUTION.md). Cumulative lat/lng start at the
        # field default (0xF0) and accumulate 16-bit signed deltas combined from
        # field pairs (87 lo + 82 hi) for LAT and (86 lo + 81 hi) for LNG.
        GPS_LONG_LO, GPS_LONG_HI = 86, 81
        GPS_LAT_LO,  GPS_LAT_HI  = 87, 82
        GPS_DEFAULT = 0xF0
        gps_lat_cum = GPS_DEFAULT
        gps_lng_cum = GPS_DEFAULT

        '''
            **NEW**
            The overall record structure quite differs from the original, simpler than expected actually.

            struct record:
                byte somevalue
                short decodeflags[2]
                // decodeflags[0] == decodeflags[1]
                byte repeatcount
                // If repeat count is non-zero, output the current data set again (incrementing timestamp) and then continue processing.

                // For each bit set in decodeflags: fieldflags[x], and signflags[x] will exist
                byte fieldflags[16];   
                byte signflags[16];

                // then there is a value for each bit set in fieldflags
                // each value is stored as a difference with the previous value, the initial value being 0xF0 or 0 depending on the field
                // some fields are stored as two bytes (EGT, RPM, etc)
        '''

        struct_flightdata = struct.Struct('!x2HB')

        td = timedelta(seconds = interval_secs)

        labels = \
        {
            'EGT1': (0, 48), 'EGT2': (1, 49), 'EGT3':(2, 50), 'EGT4': (3, 51), 'EGT5': (4, 52), 'EGT6': (5, 53),
            'CHT1': 8, 'CHT2': 9, 'CHT3': 10, 'CHT4': 11, 'CHT5': 12, 'CHT6': 13,
            'CRB': 18, 'CLD': 14, 'OILT': 15, 'MARK': 16, 'OILP': 17, 'VOLT': 20, 'OAT': 21,
            'USD': 22, 'FF': 23, 'HP': 30, 'MAP': 40, 'RPM': (41,42), 'HOURS': (78, 79),
            'GSPD': 85,
            # Added (see ATTRIBUTION.md): altitude is a delta-encoded single byte
            # at field 83. GPS lat/lng are handled separately below — not via
            # this labels map — because they use a 16-bit-combined delta scheme
            # incompatible with the standard low/high tuple pairing.
            'ALT': 83,
        }

        GSPD_index = labels['GSPD']

        #TODO: locate high byte for ground speed (GSPD) which must surely exists

        NUM_FIELDS = 128
        DEFAULT_VALUE = 0xF0
        default_values = [DEFAULT_VALUE] * NUM_FIELDS

        # special case for HP: default value is 0
        default_values[labels['HP']] = 0

        # default value for high bytes:
        for key, index in labels.items():
            if type(index) == tuple:
                default_values[index[1]] = 0


        previous_values = [None] * NUM_FIELDS
        GSPD_bug = True

        csv_header = 'date'
        csv_values = ''

        for key in labels:
            csv_header += ',' + key

        if additional_columns:
            for key in additional_columns:
                csv_header += ',' + key

        csv_header += '\n'

        count = 0
        offset = 0
        flen = len(data)
        while offset < flen - struct_flightdata.size:
            # read decode flags
            flightdata = struct_flightdata.unpack_from(data, offset)

            # Modified vs upstream (matches openenginedata.org's behaviour):
            # the two decodeflags shorts SHOULD match (per-record redundancy
            # check). When they don't, upstream asserts and dies; on real-world
            # files this kills the whole conversion. Treat it as end-of-decodable
            # data for this flight, keep what we have, move on to the next flight.
            if flightdata[0] != flightdata[1]:
                self.parseWarnings = getattr(self, 'parseWarnings', [])
                self.parseWarnings.append(
                    f"flight {fnum}: decodeflags mismatch at byte {offset} "
                    f"(0x{flightdata[0]:04x} vs 0x{flightdata[1]:04x}); "
                    f"keeping {count} decoded rows, skipping remainder"
                )
                break

            offset += struct_flightdata.size

            decodeflags = flightdata[0]
            repeatcount = flightdata[2]

            # Repeat compression: the upstream parser's TODO is to emit
            # `repeatcount` extra copies of the previous values with advancing
            # timestamps. We do exactly that AFTER decoding this record's values,
            # so the emit happens further down — here we just advance the date
            # so the cumulative offsets stay aligned. (openenginedata.org takes
            # the same partial approach.)
            for i in range(0, repeatcount): date += td

            # decode flags
            fieldflags = [0] * 16
            signflags = [0] * 16

            for i in range(0, 16): 
                if decodeflags & (1 << i):
                    fieldflags[i] = data[offset]
                    offset += 1

            for i in range(0, 16): 
                if decodeflags & (1 << i) and (i != 6 and i != 7):
                    signflags[i] = data[offset]
                    offset += 1


            # convert bits to lists for simplicity
            new_fieldflags = []
            new_signflags = []
            for f in fieldflags:
                for i in range(0,8): new_fieldflags.append(f & (1 << i))
            for f in signflags:
                for i in range(0,8): new_signflags.append(f & (1 << i))


            # sign value for high bytes is the one from the corresponding low bytes
            for key, index in labels.items():
                if type(index) == tuple:
                    new_signflags[index[1]] = new_signflags[index[0]]


            # read and calculate differences
            new_values = [None] * NUM_FIELDS

            # Capture raw (unsigned, pre-sign-flip) diff bytes for the GPS field
            # indices — the GPS scheme combines lo+hi into a 16-bit signed delta,
            # which doesn't fit python-edm's normal tuple-pairing convention.
            gps_raw = {}

            for k in range(0, NUM_FIELDS):
                value = previous_values[k]

                if new_fieldflags[k]:
                    diff = data[offset]
                    offset += 1

                    if k in (GPS_LONG_LO, GPS_LONG_HI, GPS_LAT_LO, GPS_LAT_HI):
                        gps_raw[k] = diff  # capture pre-sign-flip

                    negative = new_signflags[k]

                    if negative: diff = -diff

                    if value is None and diff == 0:
                        pass
                    else:
                        if value is None: value = default_values[k]

                        value += diff

                        previous_values[k] = value


                if value is None: value = 0

                if k == GSPD_index:
                    if value == 150 and GSPD_bug:
                        value = 0
                    elif value:
                        GSPD_bug = False

                new_values[k] = value

            # GPS delta accumulation (see ATTRIBUTION.md). The low-byte field's
            # signflag drives the sign of the combined 16-bit value. If only the
            # low byte changed, the delta is just the low byte.
            if new_fieldflags[GPS_LONG_LO]:
                lo = gps_raw[GPS_LONG_LO]
                if new_fieldflags[GPS_LONG_HI]:
                    delta = (gps_raw[GPS_LONG_HI] << 8) | lo
                else:
                    delta = lo
                if new_signflags[GPS_LONG_LO]:
                    delta = -delta
                gps_lng_cum += delta
            if new_fieldflags[GPS_LAT_LO]:
                lo = gps_raw[GPS_LAT_LO]
                if new_fieldflags[GPS_LAT_HI]:
                    delta = (gps_raw[GPS_LAT_HI] << 8) | lo
                else:
                    delta = lo
                if new_signflags[GPS_LAT_LO]:
                    delta = -delta
                gps_lat_cum += delta


            # save values
            values = {}
            values['date'] = date

            for key, index in labels.items():
                if type(index) == tuple:
                    value = new_values[index[0]] + (new_values[index[1]] << 8)
                else:
                    value = new_values[index]

                values[key] = value

            # GPS lat/lng (added — see ATTRIBUTION.md). Emit None when we have
            # no initial position, or when no GPS deltas have been accumulated
            # yet (cumulative still at the field default).
            if initial_lat is None or initial_lng is None or (
                gps_lat_cum == GPS_DEFAULT and gps_lng_cum == GPS_DEFAULT
            ):
                values['LAT'] = None
                values['LNG'] = None
            else:
                values['LAT'] = initial_lat + (gps_lat_cum - GPS_DEFAULT) / 6000
                values['LNG'] = initial_lng + (gps_lng_cum - GPS_DEFAULT) / 6000

            def f2c(t): return round((t - 32) * 5 / 9.0, 2)

            if convertEngineTemp:
                for key in [ 'EGT1', 'EGT2', 'EGT3', 'EGT4', 'EGT5', 'EGT6',
                    'CHT1', 'CHT2', 'CHT3', 'CHT4', 'CHT5', 'CHT6',
                    'CRB', 'CLD', 'OILT']:
                    values[key] = f2c(values[key])
            if convertOilTemp:
                    values['OAT'] = f2c(values['OAT'])

            if values['GSPD'] < 0: # this happens sometimes, dunno why
                values['GSPD'] = 0 

            if additional_columns:
                for key, fn in additional_columns.items():
                    values[key] = fn(fnum, date, values)


            # Modified vs upstream: capture row as a dict for in-memory consumers.
            rows.append(dict(values))

            # convert to CSV
            row = ''
            for key, value in values.items():
                row += ',' + str(value)

            csv_values += row[1:] + '\n'

            count += 1
            date += td


        # Modified vs upstream: expose decoded rows in memory.
        self.flight_rows[fnum] = rows

        # save CSV (only if an outDir was provided)
        if self.outDir:
            with open(self.outDir + '/' + self.config['TAIL NO'] + '-' + str(fnum) + '.csv', 'wt') as f:
                f.write(csv_header)
                f.write(csv_values)

        return csv_header, csv_values






