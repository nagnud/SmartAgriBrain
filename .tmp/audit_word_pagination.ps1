param(
    [Parameter(Mandatory = $true)]
    [string]$DocumentPath
)

$resolved = (Resolve-Path -LiteralPath $DocumentPath).Path
$word = $null
$document = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($resolved, $false, $true)
    $document.Repaginate()

    $pageCount = $document.ComputeStatistics(2)
    $paragraphCount = $document.Paragraphs.Count
    $headings = @()
    $orphans = @()
    $splitFigures = @()
    $figures = @()
    $pageParagraphs = @{}

    for ($index = 1; $index -le $paragraphCount; $index++) {
        $paragraph = $document.Paragraphs.Item($index)
        $text = ($paragraph.Range.Text -replace '[\r\a]', '').Trim()
        $startRange = $document.Range($paragraph.Range.Start, [Math]::Min($paragraph.Range.Start + 1, $document.Content.End))
        $page = $startRange.Information(1)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($startRange)
        if (-not $pageParagraphs.ContainsKey($page)) {
            $pageParagraphs[$page] = 0
        }
        if ($text.Length -gt 0) {
            $pageParagraphs[$page]++
        }

        $styleName = [string]$paragraph.Range.Style.NameLocal
        $outlineLevel = [int]$paragraph.OutlineLevel
        if ($outlineLevel -ge 1 -and $outlineLevel -le 3) {
            $headings += [pscustomobject]@{
                Index = $index
                Page = $page
                Style = $styleName
                Level = $outlineLevel
                Text = $text
            }

            $nextPage = $page
            for ($next = $index + 1; $next -le $paragraphCount; $next++) {
                $nextParagraph = $document.Paragraphs.Item($next)
                $nextText = ($nextParagraph.Range.Text -replace '[\r\a]', '').Trim()
                if ($nextText.Length -gt 0) {
                    $nextStartRange = $document.Range($nextParagraph.Range.Start, [Math]::Min($nextParagraph.Range.Start + 1, $document.Content.End))
                    $nextPage = $nextStartRange.Information(1)
                    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($nextStartRange)
                    break
                }
            }
            if ($nextPage -gt $page) {
                $orphans += [pscustomobject]@{
                    Index = $index
                    Page = $page
                    Style = $styleName
                    Level = $outlineLevel
                    Text = $text
                    NextPage = $nextPage
                }
            }
        }

        if ($paragraph.Range.InlineShapes.Count -gt 0) {
            $captionText = ""
            $captionPage = $page
            for ($next = $index + 1; $next -le $paragraphCount; $next++) {
                $nextParagraph = $document.Paragraphs.Item($next)
                $nextText = ($nextParagraph.Range.Text -replace '[\r\a]', '').Trim()
                if ($nextText.Length -gt 0) {
                    $captionText = $nextText
                    $nextStartRange = $document.Range($nextParagraph.Range.Start, [Math]::Min($nextParagraph.Range.Start + 1, $document.Content.End))
                    $captionPage = $nextStartRange.Information(1)
                    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($nextStartRange)
                    break
                }
            }
            $figure = [pscustomobject]@{
                Index = $index
                Page = $page
                CaptionPage = $captionPage
                Caption = $captionText
            }
            $figures += $figure
            if ($captionPage -ne $page) {
                $splitFigures += $figure
            }
        }
    }

    $blankPages = @()
    for ($page = 1; $page -le $pageCount; $page++) {
        if (-not $pageParagraphs.ContainsKey($page) -or $pageParagraphs[$page] -eq 0) {
            $blankPages += $page
        }
    }

    Write-Output "pages=$pageCount"
    Write-Output "paragraphs=$paragraphCount"
    Write-Output "headings=$($headings.Count)"
    Write-Output "orphan_headings=$($orphans.Count)"
    Write-Output "blank_pages=$($blankPages -join ',')"
    Write-Output "figures=$($figures.Count)"
    Write-Output "split_figures=$($splitFigures.Count)"
    if ($orphans.Count -gt 0) {
        $orphans | Format-Table -AutoSize | Out-String | Write-Output
    }
    if ($figures.Count -gt 0) {
        $figures | Format-Table -AutoSize | Out-String | Write-Output
    }
    Write-Output "chapter_pages:"
    $headings |
        Where-Object { $_.Level -eq 1 } |
        Format-Table -AutoSize |
        Out-String |
        Write-Output
}
finally {
    if ($document -ne $null) {
        $document.Close($false)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($document)
    }
    if ($word -ne $null) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
