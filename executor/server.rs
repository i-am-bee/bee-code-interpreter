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
use serde::{Deserialize, Serialize};
use std::collections::{HashSet, HashMap};
use std::env;
use std::path::Path;
use std::time::{Duration, SystemTime};
use tempfile::TempDir;
use tokio::fs::{self, OpenOptions};
use tokio::io::{AsyncWriteExt, AsyncBufReadExt};
use tokio::process::Command;
use std::os::unix::fs::MetadataExt;
use std::time::UNIX_EPOCH;

#[derive(Serialize, Deserialize)]
struct ExecuteRequest {
    source_code: String,
    timeout: Option<u64>,
    env: Option<HashMap<String, String>>,
}

#[derive(Serialize)]
struct ExecuteResult {
    stdout: String,
    stderr: String,
    exit_code: i32,
    files: Vec<String>,
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

async fn get_changed_files(dir: &str, since: SystemTime) -> Vec<String> {
    let mut changed_files = Vec::new();
    let mut read_dir = fs::read_dir(dir).await.unwrap();
    while let Some(entry) = read_dir.next_entry().await.unwrap() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        if let Ok(metadata) = entry.metadata().await {
            let ctime = metadata.ctime();
            let ctime_nanos = metadata.ctime_nsec();
            let change_time = UNIX_EPOCH + Duration::new(ctime as u64, ctime_nanos as u32);
            if change_time > since {
                if let Some(path_str) = path.to_str() {
                    changed_files.push(path_str.to_string());
                }
            }
        }
    }
    changed_files
}

async fn execute(payload: web::Json<ExecuteRequest>) -> Result<HttpResponse, Error> {
    let workspace = env::var("APP_WORKSPACE").unwrap_or_else(|_| "/workspace".to_string());
    let execution_start_time = SystemTime::now();
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

    tokio::fs::rename(source_dir.path().join("script.py"), source_dir.path().join("script.xsh")).await?;
    
    let timeout = Duration::from_secs(payload.timeout.unwrap_or(60));
    let mut cmd = Command::new("xonsh"); // TODO: manually switch between python and shell for ~80ms perf gain
    cmd.arg(source_dir.path().join("script.xsh"));
    if let Some(env) = &payload.env { cmd.envs(env); }
    let (stdout, stderr, exit_code) = tokio::time::timeout(
        timeout,
        cmd.output(),
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
    
    let files = get_changed_files(&workspace, execution_start_time).await;

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