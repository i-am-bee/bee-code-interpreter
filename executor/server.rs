// Copyright 2024 IBM Corp.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use actix_web::{middleware::Logger, web, App, Error, HttpResponse, HttpServer};
use futures::StreamExt;
use futures::TryStreamExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::env;
use std::path::Path;
use std::time::Duration;
use tempfile::TempDir;
use tokio_stream::wrappers::ReadDirStream;
use tokio_util::io::ReaderStream;
use tokio::fs::{self, OpenOptions};
use tokio::io::{AsyncWriteExt, AsyncBufReadExt};
use tokio::process::Command;

#[derive(Serialize, Deserialize)]
struct ExecuteRequest {
    source_code: String,
    timeout: Option<u64>,
}

#[derive(Serialize)]
struct ExecuteResult {
    stdout: String,
    stderr: String,
    exit_code: i32,
    files: Vec<File>,
}

#[derive(Serialize)]
struct File {
    path: String,
    old_hash: Option<String>,
    new_hash: Option<String>,
}

static REQUIREMENTS: std::sync::LazyLock<HashSet<String>> = std::sync::LazyLock::new(|| {
    tokio::runtime::Runtime::new().unwrap().block_on(async {
        let mut requirements = HashSet::new();
        let file = tokio::fs::File::open("/requirements.txt").await.unwrap();
        let reader = tokio::io::BufReader::new(file);
        let mut lines = reader.lines();
        while let Some(line) = lines.next_line().await.unwrap() {
            let requirement = line.split(&['#', '['][..]).next().unwrap_or(&line).trim().to_string();
            if !requirement.is_empty() {
                requirements.insert(requirement);
            }
        }
        let skip_file = tokio::fs::File::open("/requirements-skip.txt").await.unwrap();
        let skip_reader = tokio::io::BufReader::new(skip_file);
        let mut skip_lines = skip_reader.lines();
        while let Some(line) = skip_lines.next_line().await.unwrap() {
            let requirement = line.split(&['#', '['][..]).next().unwrap_or(&line).trim().to_string();
            if !requirement.is_empty() {
                requirements.insert(requirement);
            }
        }
        requirements
    })
});

async fn upload_file(
    mut payload: web::Payload,
    path: web::Path<String>,
) -> Result<HttpResponse, Error> {
    let workspace = env::var("APP_WORKSPACE").unwrap_or_else(|_| "/workspace".to_string());
    let file_path = format!("{}/{}", workspace, path);
    let file_dir = Path::new(&file_path).parent().unwrap();
    fs::create_dir_all(file_dir).await?;
    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(file_path)
        .await?;
    while let Some(chunk) = payload.next().await {
        let data = chunk?;
        file.write_all(&data).await?;
    }
    Ok(HttpResponse::NoContent().finish())
}

async fn download_file(path: web::Path<String>) -> Result<HttpResponse, Error> {
    let workspace = env::var("APP_WORKSPACE").unwrap_or_else(|_| "/workspace".to_string());
    let file = tokio::fs::File::open(format!("{}/{}", workspace, path)).await?;
    Ok(HttpResponse::Ok()
        .content_type("application/octet-stream")
        .streaming(tokio_util::io::ReaderStream::new(file)))
}

async fn calculate_sha256(path: &str) -> Result<String, Box<dyn std::error::Error>> {
    let file = tokio::fs::File::open(path).await?;
    let stream = ReaderStream::new(file);
    let mut hasher = Sha256::new();
    let mut stream = stream.map_err(|e: std::io::Error| e);
    while let Some(chunk) = stream.try_next().await? { hasher.update(&chunk); }
    Ok(format!("{:x}", hasher.finalize()))
}

async fn get_file_hashes(dir: &str) -> HashMap<String, String> {
    let mut hashes = HashMap::new();
    let mut entries = ReadDirStream::new(tokio::fs::read_dir(dir).await.unwrap());
    while let Some(Ok(entry)) = entries.next().await {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        if let Some(path_str) = path.to_str() {
            if let Ok(hash) = calculate_sha256(path_str).await {
                hashes.insert(path_str.to_string(), hash);
            }
        }
    }
    hashes
}

async fn execute(payload: web::Json<ExecuteRequest>) -> Result<HttpResponse, Error> {
    let workspace = env::var("APP_WORKSPACE").unwrap_or_else(|_| "/workspace".to_string());
    let before_hashes = get_file_hashes(&workspace).await;
    let source_dir = TempDir::new()?;
    
    tokio::fs::write(source_dir.path().join("script.py"), &payload.source_code).await?;
    let guessed_deps = String::from_utf8_lossy(
        &Command::new("upm")
            .arg("guess")
            .current_dir(source_dir.path())
            .output()
            .await?
            .stdout,
    ).trim().to_string();

    let new_deps: Vec<&str> = guessed_deps
        .split_whitespace()
        .filter(|dep| !REQUIREMENTS.contains(*dep))
        .collect();

    if !new_deps.is_empty() {
        Command::new("pip")
            .arg("install")
            .arg("--no-cache-dir")
            .args(&new_deps)
            .output()
            .await?;
    }
    
    let timeout = Duration::from_secs(payload.timeout.unwrap_or(60));
    let (stdout, stderr, exit_code) = tokio::time::timeout(
        timeout,
        Command::new("xonsh") // TODO: manually switch between python and shell for ~80ms perf gain
            .arg(source_dir.path().join("script.py"))
            .output(),
    )
    .await
    .map(|r| {
        r.map(|o| {
            (
                String::from_utf8_lossy(&o.stdout).to_string(),
                String::from_utf8_lossy(&o.stderr).to_string(),
                o.status.code().unwrap_or(-1),
            )
        })
    })
    .unwrap_or_else(|_| Ok((String::new(), "Execution timed out".to_string(), -1)))?;
    let after_hashes = get_file_hashes(&workspace).await;
    let files = before_hashes
        .iter()
        .map(|(path, old_hash)| File {
            path: path.clone(),
            old_hash: Some(old_hash.clone()),
            new_hash: after_hashes.get(path).cloned(),
        })
        .chain(
            after_hashes
                .iter()
                .filter(|(path, _)| !before_hashes.contains_key(*path))
                .map(|(path, new_hash)| File {
                    path: path.clone(),
                    old_hash: None,
                    new_hash: Some(new_hash.clone()),
                }),
        )
        .collect();

    Ok(HttpResponse::Ok().json(ExecuteResult {
        stdout,
        stderr,
        exit_code,
        files,
    }))
}

#[actix_web::main]
async fn web() -> std::io::Result<()> {
    env_logger::init_from_env(env_logger::Env::new().default_filter_or("info"));
    let listen_addr = env::var("APP_LISTEN_ADDR").unwrap_or_else(|_| "0.0.0.0:8000".to_string());

    HttpServer::new(|| {
        App::new()
            .wrap(Logger::default())
            .route("/workspace/{path:.*}", web::put().to(upload_file))
            .route("/workspace/{path:.*}", web::get().to(download_file))
            .route("/execute", web::post().to(execute))
    })
    .bind(&listen_addr)?
    .run()
    .await
}

fn main() -> std::io::Result<()> {
    std::sync::LazyLock::force(&REQUIREMENTS);
    web()
}