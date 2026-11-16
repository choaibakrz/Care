//! Journal segment files (one JSON record per line, rotated at `segment_max_bytes`).

use std::fs::File;
use std::path::{Path, PathBuf};

use crate::error::JournalError;

/// What the end of the last segment looks like on start.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TailState {
    /// Last complete record.
    pub last_seq: Option<u64>,
    /// Its hash (zeros for an empty journal).
    pub last_hash: [u8; 32],
    /// A half-written last line was found (expected after a power cut).
    pub torn: bool,
}

/// An open segment.
#[derive(Debug)]
pub struct Segment {
    path: PathBuf,
    file: File,
    bytes: u64,
    index: u32,
}

impl Segment {
    /// Opens the last segment in `dir` (creating the first), verifying its tail.
    ///
    /// A torn last line (a crash in the middle of a write) is left as it is and a new
    /// segment is started, so the evidence stays and `journal verify` reports it as a torn
    /// tail, not as tampering.
    ///
    /// # Errors
    /// `Io`; `Corrupt` for a damaged line that is not the last.
    pub fn open_last(dir: &Path) -> Result<(Segment, TailState), JournalError> {
        std::fs::create_dir_all(dir).map_err(io("create the journal directory", dir))?;
        let mut tail = TailState {
            last_seq: None,
            last_hash: [0; 32],
            torn: false,
        };
        let segments = segment_files(dir)?;
        let mut index = 1;
        for (segment_index, path) in &segments {
            let read = read_segment(path)?;
            if let Some(record) = read.records.last() {
                tail.last_seq = Some(record.seq);
                tail.last_hash = record.hash;
            }
            tail.torn = read.torn;
            index = *segment_index;
        }
        if tail.torn {
            index += 1;
        }
        let segment = Segment::open(dir, index)?;
        Ok((segment, tail))
    }

    /// Opens (or creates) segment `index` of `dir` for appending.
    fn open(dir: &Path, index: u32) -> Result<Segment, JournalError> {
        let path = dir.join(segment_name(index));
        let file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
            .map_err(io("open the journal segment", &path))?;
        let bytes = file
            .metadata()
            .map_err(io("read the journal segment size", &path))?
            .len();
        Ok(Segment {
            path,
            file,
            bytes,
            index,
        })
    }

    /// Appends one line (without fsync).
    ///
    /// # Errors
    /// `Io`.
    pub fn append_line(&mut self, line: &[u8]) -> Result<(), JournalError> {
        use std::io::Write as _;
        let mut buffer = Vec::with_capacity(line.len() + 1);
        buffer.extend_from_slice(line);
        buffer.push(b'\n');
        self.file
            .write_all(&buffer)
            .map_err(io("write to the journal segment", &self.path))?;
        self.bytes += u64::try_from(buffer.len()).unwrap_or(u64::MAX);
        Ok(())
    }

    /// Flushes to disk.
    ///
    /// # Errors
    /// `Io`.
    pub fn sync(&mut self) -> Result<(), JournalError> {
        self.file
            .sync_data()
            .map_err(io("flush the journal segment", &self.path))
    }

    /// Starts the next segment.
    ///
    /// # Errors
    /// `Io`.
    pub fn rotate(&mut self, dir: &Path) -> Result<Segment, JournalError> {
        self.sync()?;
        Segment::open(dir, self.index + 1)
    }

    /// Size so far.
    #[must_use]
    pub fn bytes(&self) -> u64 {
        self.bytes
    }

    /// Path.
    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }
}

/// `segment-000001.jsonl`.
fn segment_name(index: u32) -> String {
    format!("segment-{index:06}.jsonl")
}

fn io(action: &'static str, path: &Path) -> impl FnOnce(std::io::Error) -> JournalError {
    let path = path.to_path_buf();
    move |source| JournalError::Io {
        action,
        path,
        source,
    }
}

/// The segment files of `dir` with their index, in order.
///
/// # Errors
/// `Io`.
pub fn segment_files(dir: &Path) -> Result<Vec<(u32, PathBuf)>, JournalError> {
    let mut found = Vec::new();
    let entries = std::fs::read_dir(dir).map_err(io("read the journal directory", dir))?;
    for entry in entries {
        let path = entry.map_err(io("read the journal directory", dir))?.path();
        let index = path
            .file_name()
            .and_then(|name| name.to_str())
            .and_then(|name| name.strip_prefix("segment-"))
            .and_then(|rest| rest.strip_suffix(".jsonl"))
            .and_then(|digits| digits.parse::<u32>().ok());
        if let Some(index) = index {
            found.push((index, path));
        }
    }
    found.sort();
    Ok(found)
}

/// What one segment file holds.
#[derive(Debug, Default)]
pub struct SegmentRead {
    /// The records that parse, in file order.
    pub records: Vec<crate::record::JournalRecord>,
    /// Line numbers (1-based) of lines that do not parse, other than a torn last line.
    pub damaged: Vec<u64>,
    /// The last line is incomplete (no final newline and does not parse).
    pub torn: bool,
}

/// Reads one segment file.
///
/// # Errors
/// `Io`.
pub fn read_segment(path: &Path) -> Result<SegmentRead, JournalError> {
    let bytes = std::fs::read(path).map_err(io("read the journal segment", path))?;
    let text = String::from_utf8_lossy(&bytes);
    let ends_cleanly = text.is_empty() || text.ends_with('\n');
    let lines: Vec<&str> = text.lines().collect();
    let mut read = SegmentRead::default();
    for (number, line) in lines.iter().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        match serde_json::from_str::<crate::record::JournalRecord>(line) {
            Ok(record) => read.records.push(record),
            Err(_) if number + 1 == lines.len() && !ends_cleanly => read.torn = true,
            Err(_) => read
                .damaged
                .push(u64::try_from(number + 1).unwrap_or(u64::MAX)),
        }
    }
    Ok(read)
}
